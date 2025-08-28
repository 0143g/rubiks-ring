#!/usr/bin/env python3
"""
V2 Cube Controller - Clean Implementation
Direct BLE to Gamepad with no threading complexity
"""

import asyncio
import time
import json
import sys
import os
from pathlib import Path
import vgamepad as vg
import keyboard

# Add parent directory for gan_web_bluetooth
sys.path.append(str(Path(__file__).parent.parent))
from gan_web_bluetooth import GanSmartCube
from gan_web_bluetooth.protocols.base import (
    GanCubeMoveEvent,
    GanCubeOrientationEvent,
    GanCubeBatteryEvent
)

class CubeControllerClean:
    """Clean cube controller - pure async, no threads"""

    def __init__(self):
        # Config management
        self.current_config_path = None
        self.config = self.load_config()
        self.config_mtime = 0  # Track modification time

        # Cube connection
        self.cube = None

        # Gamepad
        self.gamepad = vg.VX360Gamepad()
        self.gamepad_dirty = False  # Track when gamepad needs update

        # State tracking
        self.calibration_ref = None
        self.last_quaternion = None
        self.last_move = None
        self.last_move_time = 0
        self.sprinting = False
        self.pending_sprint_state = None  # For sprint task
        self.current_joy_y = 0  # Track for sprint detection

        # Performance - rate limit orientation
        self.last_update = 0
        self.update_interval = 8  # 125Hz max

        # Stats
        self.orientation_count = 0
        self.move_count = 0
        self.start_time = 0

        # Debug
        self.debug_moves = True  # Toggle to see move arrival times

        print("V2 Clean Controller initialized")
        print(f"Loaded {len(self.config.get('move_mappings', {}))} mappings")

    def load_config(self, config_name="controller_config.json"):
        """Load configuration from JSON file"""
        paths = [
            Path(config_name),
            Path(__file__).parent / config_name,
            Path(__file__).parent.parent / config_name
        ]

        for path in paths:
            if path.exists():
                with open(path, 'r') as f:
                    self.current_config_path = path
                    # Track modification time for hot reload
                    self.config_mtime = os.path.getmtime(path)
                    config = json.load(f)
                    print(f"Config loaded from: {path}")
                    print(f"Loaded {len(config.get('move_mappings', {}))} mappings")
                    return config

        print(f"No config found ({config_name}), using defaults")
        return {"move_mappings": {}}
    
    def reload_config(self):
        """Reload configuration from current file"""
        if self.current_config_path and self.current_config_path.exists():
            try:
                with open(self.current_config_path, 'r') as f:
                    new_config = json.load(f)
                    self.config = new_config
                    self.config_mtime = os.path.getmtime(self.current_config_path)
                    print(f"✅ Config reloaded from: {self.current_config_path}")
                    print(f"Active mappings: {len(self.config.get('move_mappings', {}))}")
                    return True
            except Exception as e:
                print(f"⚠️ Error reloading config: {e}")
        return False
    
    def switch_config(self, config_name):
        """Switch to a different config file"""
        old_path = self.current_config_path
        self.config = self.load_config(config_name)
        if self.current_config_path != old_path:
            print(f"🔄 Switched config to: {config_name}")
            return True
        return False

    def handle_orientation(self, event: GanCubeOrientationEvent):
        """Direct handler - NO executor, NO threads"""
        now_ms = time.perf_counter_ns() // 1_000_000

        # Rate limit to 125Hz
        if now_ms - self.last_update < self.update_interval:
            return
        self.last_update = now_ms

        # Extract quaternion
        qx = event.quaternion.x
        qy = event.quaternion.y
        qz = event.quaternion.z
        qw = event.quaternion.w

        # Store for calibration
        self.last_quaternion = (qx, qy, qz, qw)

        # Apply calibration if set
        if self.calibration_ref:
            qx, qy, qz, qw = self.apply_calibration(qx, qy, qz, qw)

        # Get sensitivity
        sens = self.config.get('sensitivity', {})
        x_sens = sens.get('tilt_x_sensitivity', 2.5)
        y_sens = sens.get('tilt_y_sensitivity', 2.5)
        z_sens = sens.get('spin_z_sensitivity', 2.0)

        # Direct mapping to joystick
        joy_x = qy * x_sens * 2  # left/right
        joy_y = -qx * y_sens * 2  # forward/back
        joy_z = -qz * z_sens  # rotation

        # Deadzone
        deadzone = self.config.get('deadzone', {}).get('general_deadzone', 0.1)
        spin_dz = self.config.get('deadzone', {}).get('spin_deadzone', 0.085)

        if abs(joy_x) < deadzone: joy_x = 0
        if abs(joy_y) < deadzone: joy_y = 0
        if abs(joy_z) < spin_dz: joy_z = 0

        # Clamp values
        joy_x = max(-1.0, min(1.0, joy_x))
        joy_y = max(-1.0, min(1.0, joy_y))
        joy_z = max(-1.0, min(1.0, joy_z))

        # Update gamepad - IMMEDIATE update for orientation
        self.gamepad.left_joystick_float(x_value_float=joy_x, y_value_float=joy_y)
        self.gamepad.right_joystick_float(x_value_float=joy_z, y_value_float=0)
        self.gamepad.update()

        # Track for sprint detection (handled by separate task)
        self.current_joy_y = joy_y
        self.orientation_count += 1

    def handle_move(self, event: GanCubeMoveEvent):
        """Direct handler - NO threads for button releases"""
        move = event.move
        now_ms = time.perf_counter_ns() // 1_000_000

        # Debug: show move arrival
        if self.debug_moves:
            print(f"[{time.perf_counter():.3f}] Move received: {move}")

        # Duplicate check
        if move == self.last_move and (now_ms - self.last_move_time) < 50:
            if self.debug_moves:
                print(f"  -> Duplicate, skipping")
            return
        self.last_move = move
        self.last_move_time = now_ms

        self.move_count += 1

        # Special roll handling
        if move == "U'" and self.sprinting:
            asyncio.create_task(self.execute_roll())
            return

        # Get mapping
        action = self.config.get('move_mappings', {}).get(move)
        if not action:
            if self.debug_moves:
                print(f"  -> No mapping found")
            return

        if self.debug_moves:
            print(f"  -> Action: {action}")

        # Execute action with IMMEDIATE updates
        if action.startswith('gamepad_combo_'):
            asyncio.create_task(self.execute_combo(action))
        elif action == 'gamepad_r2':
            self.gamepad.right_trigger(255)
            self.gamepad.update()  # IMMEDIATE update
            asyncio.create_task(self.release_trigger_later('right', 0.1))
        elif action == 'gamepad_l2':
            self.gamepad.left_trigger(255)
            self.gamepad.update()  # IMMEDIATE update
            asyncio.create_task(self.release_trigger_later('left', 0.1))
        else:
            button = self.get_button(action)
            if button:
                self.gamepad.press_button(button)
                self.gamepad.update()  # IMMEDIATE update for button press
                asyncio.create_task(self.release_button_later(button, 0.1))

    async def release_button_later(self, button, delay):
        """Async release - NO THREADS"""
        await asyncio.sleep(delay)
        self.gamepad.release_button(button)
        self.gamepad.update()  # Update after release

    async def release_trigger_later(self, side, delay):
        """Async trigger release - NO THREADS"""
        await asyncio.sleep(delay)
        if side == 'right':
            self.gamepad.right_trigger(0)
        else:
            self.gamepad.left_trigger(0)
        self.gamepad.update()  # Update after release

    async def execute_roll(self):
        """Handle roll during sprint"""
        print("Rolling...")
        # Release B
        self.gamepad.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
        self.gamepad.update()
        await asyncio.sleep(0.05)

        # Tap B
        self.gamepad.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
        self.gamepad.update()
        await asyncio.sleep(0.1)

        self.gamepad.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
        self.gamepad.update()
        await asyncio.sleep(0.05)

        # Re-hold if still sprinting
        if self.sprinting:
            self.gamepad.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
            self.gamepad.update()

    async def execute_combo(self, action):
        """Execute button combo"""
        combo = action.replace('gamepad_combo_', '').split('+')
        if len(combo) != 2:
            return

        button_map = {
            'y': vg.XUSB_BUTTON.XUSB_GAMEPAD_Y,
            'dpad_down': vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN,
            'dpad_up': vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP,
            'dpad_left': vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT,
            'dpad_right': vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT,
            'r1': vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER,
        }

        b1 = button_map.get(combo[0])
        b2 = button_map.get(combo[1])

        if b1 and b2:
            self.gamepad.press_button(b1)
            # No update yet
            await asyncio.sleep(0.05)

            self.gamepad.press_button(b2)
            self.gamepad.update()  # Single update after both pressed
            await asyncio.sleep(0.1)

            self.gamepad.release_button(b2)
            self.gamepad.release_button(b1)
            self.gamepad.update()  # Single update after both released

    def get_button(self, action):
        """Map action to button"""
        button_map = {
            'gamepad_a': vg.XUSB_BUTTON.XUSB_GAMEPAD_A,
            'gamepad_b': vg.XUSB_BUTTON.XUSB_GAMEPAD_B,
            'gamepad_x': vg.XUSB_BUTTON.XUSB_GAMEPAD_X,
            'gamepad_y': vg.XUSB_BUTTON.XUSB_GAMEPAD_Y,
            'gamepad_l1': vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER,
            'gamepad_r1': vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER,
            'gamepad_r3': vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB,
            'gamepad_dpad_up': vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP,
            'gamepad_dpad_down': vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN,
            'gamepad_dpad_left': vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT,
            'gamepad_dpad_right': vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT,
        }
        return button_map.get(action)

    def apply_calibration(self, qx, qy, qz, qw):
        """Apply calibration quaternion math"""
        ref_x, ref_y, ref_z, ref_w = self.calibration_ref

        # Normalize reference
        norm = (ref_x**2 + ref_y**2 + ref_z**2 + ref_w**2) ** 0.5
        if norm > 0:
            ref_x /= norm
            ref_y /= norm
            ref_z /= norm
            ref_w /= norm
        else:
            ref_x, ref_y, ref_z, ref_w = 0, 0, 0, 1

        # Inverse of reference
        inv_x = -ref_x
        inv_y = -ref_y
        inv_z = -ref_z
        inv_w = ref_w

        # Relative rotation
        new_x = inv_w*qx + inv_x*qw + inv_y*qz - inv_z*qy
        new_y = inv_w*qy - inv_x*qz + inv_y*qw + inv_z*qx
        new_z = inv_w*qz + inv_x*qy - inv_y*qx + inv_z*qw
        new_w = inv_w*qw - inv_x*qx - inv_y*qy - inv_z*qz

        return new_x, new_y, new_z, new_w

    def calibrate(self):
        """Calibrate to current position"""
        if not self.last_quaternion:
            print("No orientation data yet")
            return

        self.calibration_ref = self.last_quaternion

        # Reset sprint
        if self.sprinting:
            self.sprinting = False
            self.gamepad.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
            self.gamepad.update()

        print(f"âœ… Calibrated at {self.calibration_ref}")

    def reset_camera_joystick(self):
        """Reset the right joystick (camera) to center"""
        self.gamepad.right_joystick_float(x_value_float=0.0, y_value_float=0.0)
        self.gamepad.update()
        print("ðŸŽ¯ Camera joystick reset to center")

    def toggle_debug(self):
        """Toggle move debug output"""
        self.debug_moves = not self.debug_moves
        print(f"Move debug: {'ON' if self.debug_moves else 'OFF'}")
    
    def load_config_1(self):
        """Load controller_config.json (F9)"""
        if self.switch_config("controller_config.json"):
            print("[F9] Loaded config 1")
    
    def load_config_2(self):
        """Load controller_config2.json (F10)"""
        if self.switch_config("controller_config2.json"):
            print("[F10] Loaded config 2")

    async def sprint_task(self):
        """Handle sprint state at 10Hz to avoid rapid on/off"""
        while True:
            await asyncio.sleep(0.1)  # 10Hz

            # Check if sprint state should change
            if self.current_joy_y > 0.7 and not self.sprinting:
                self.sprinting = True
                self.gamepad.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
                self.gamepad.update()  # IMMEDIATE update for sprint
                print("Sprint: ON")
            elif self.current_joy_y < 0.6 and self.sprinting:
                self.sprinting = False
                self.gamepad.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
                self.gamepad.update()  # IMMEDIATE update for sprint
                print("Sprint: OFF")

    async def stats_loop(self):
        """Print performance stats"""
        while True:
            await asyncio.sleep(5)
            if self.start_time > 0:
                runtime = time.perf_counter() - self.start_time
                ori_rate = self.orientation_count / runtime if runtime > 0 else 0
                move_rate = self.move_count / runtime if runtime > 0 else 0
                print(f"ðŸ“Š Stats: {runtime:.0f}s | Orientation: {ori_rate:.1f}Hz | Moves: {move_rate:.2f}Hz")

                # Warn if rates are low
                if ori_rate < 10:
                    print("  âš ï¸ LOW orientation rate - check BLE connection")
    
    async def config_watcher(self):
        """Watch config file for changes and hot reload"""
        while True:
            await asyncio.sleep(1)  # Check every second
            
            if self.current_config_path and self.current_config_path.exists():
                try:
                    current_mtime = os.path.getmtime(self.current_config_path)
                    if current_mtime > self.config_mtime:
                        print("🔄 Config file changed, reloading...")
                        self.reload_config()
                except Exception as e:
                    # Ignore errors (file might be in the middle of being saved)
                    pass

    async def keyboard_task(self):
        """Handle keyboard shortcuts"""
        # Set up keyboard hooks
        keyboard.add_hotkey('f5', self.calibrate)
        keyboard.add_hotkey('f6', self.reset_camera_joystick)
        keyboard.add_hotkey('f7', self.toggle_debug)
        keyboard.add_hotkey('f9', self.load_config_1)
        keyboard.add_hotkey('f10', self.load_config_2)

        print("⌨️  F5: Calibrate | F6: Reset camera | F7: Debug")
        print("⌨️  F9: Config 1 | F10: Config 2")

        # Keep running to handle keyboard events
        while True:
            await asyncio.sleep(0.1)

    async def connect(self):
        """Simple connection"""
        self.cube = GanSmartCube()

        # Direct handlers - NO executor.submit()
        self.cube.on('orientation', self.handle_orientation)
        self.cube.on('move', self.handle_move)
        self.cube.on('battery', lambda e: print(f"ðŸ”‹ Battery: {e.level}%"))

        await self.cube.connect()
        print("âœ… Connected")
        self.start_time = time.perf_counter()

        # Auto-calibrate after 2 seconds
        await asyncio.sleep(2)
        if self.last_quaternion:
            self.calibrate()
            print("ðŸ“ Place cube with GREEN face forward")


async def main():
    controller = CubeControllerClean()

    try:
        await controller.connect()

        # Start background tasks (NO update_loop anymore)
        sprint_task = asyncio.create_task(controller.sprint_task())
        stats_task = asyncio.create_task(controller.stats_loop())
        keyboard_task = asyncio.create_task(controller.keyboard_task())
        config_watcher = asyncio.create_task(controller.config_watcher())

        print("\n✅ Ready! Move cube to control.")
        print("Hot reload enabled - config changes apply automatically")
        print("Press Ctrl+C to exit\n")

        # Just wait forever
        await asyncio.Future()

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        controller.gamepad.reset()
        controller.gamepad.update()
        if controller.cube:
            await controller.cube.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
