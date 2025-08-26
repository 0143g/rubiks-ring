#!/usr/bin/env python3
"""
V2 Cube Controller - Clean Implementation
Direct BLE to Gamepad with no threading complexity
"""

import asyncio
import time
import json
import sys
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
        # Load config
        self.config = self.load_config()
        
        # Cube connection
        self.cube = None
        
        # Gamepad
        self.gamepad = vg.VX360Gamepad()
        
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
        
        print("V2 Clean Controller initialized")
        print(f"Loaded {len(self.config.get('move_mappings', {}))} mappings")
    
    def load_config(self):
        """Load configuration from JSON file"""
        paths = [
            Path("controller_config.json"),
            Path(__file__).parent / "controller_config.json",
            Path(__file__).parent.parent / "controller_config.json"
        ]
        
        for path in paths:
            if path.exists():
                with open(path, 'r') as f:
                    print(f"Config loaded from: {path}")
                    return json.load(f)
        
        print("No config found, using defaults")
        return {"move_mappings": {}}
    
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
        
        # Update gamepad - single update() call
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
        
        # Duplicate check
        if move == self.last_move and (now_ms - self.last_move_time) < 50:
            return
        self.last_move = move
        self.last_move_time = now_ms
        
        print(f"Move: {move}")
        self.move_count += 1
        
        # Special roll handling
        if move == "U'" and self.sprinting:
            asyncio.create_task(self.execute_roll())
            return
        
        # Get mapping
        action = self.config.get('move_mappings', {}).get(move)
        if not action:
            return
        
        # Execute action
        if action.startswith('gamepad_combo_'):
            asyncio.create_task(self.execute_combo(action))
        elif action == 'gamepad_r2':
            self.gamepad.right_trigger(255)
            # No update() here - let periodic task handle it
            asyncio.create_task(self.release_trigger_later('right', 0.1))
        elif action == 'gamepad_l2':
            self.gamepad.left_trigger(255)
            # No update() here - let periodic task handle it
            asyncio.create_task(self.release_trigger_later('left', 0.1))
        else:
            button = self.get_button(action)
            if button:
                self.gamepad.press_button(button)
                # No update() here - let periodic task handle it
                asyncio.create_task(self.release_button_later(button, 0.1))
    
    async def release_button_later(self, button, delay):
        """Async release - NO THREADS"""
        await asyncio.sleep(delay)
        self.gamepad.release_button(button)
        # No update() - let periodic task handle it
    
    async def release_trigger_later(self, side, delay):
        """Async trigger release - NO THREADS"""
        await asyncio.sleep(delay)
        if side == 'right':
            self.gamepad.right_trigger(0)
        else:
            self.gamepad.left_trigger(0)
        # No update() - let periodic task handle it
    
    async def execute_roll(self):
        """Handle roll during sprint"""
        print("Rolling...")
        # Release B
        self.gamepad.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
        await asyncio.sleep(0.05)
        
        # Tap B
        self.gamepad.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
        await asyncio.sleep(0.1)
        
        self.gamepad.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
        await asyncio.sleep(0.05)
        
        # Re-hold if still sprinting
        if self.sprinting:
            self.gamepad.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
    
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
        
        print(f"✅ Calibrated at {self.calibration_ref}")
    
    def reset_camera_joystick(self):
        """Reset the right joystick (camera) to center"""
        self.gamepad.right_joystick_float(x_value_float=0.0, y_value_float=0.0)
        self.gamepad.update()
        print("🎯 Camera joystick reset to center")
    
    async def sprint_task(self):
        """Handle sprint state at 10Hz to avoid rapid on/off"""
        while True:
            await asyncio.sleep(0.1)  # 10Hz
            
            # Check if sprint state should change
            if self.current_joy_y > 0.7 and not self.sprinting:
                self.sprinting = True
                self.gamepad.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
                print("Sprint: ON")
            elif self.current_joy_y < 0.6 and self.sprinting:
                self.sprinting = False
                self.gamepad.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
                print("Sprint: OFF")
    
    async def update_loop(self):
        """Periodic gamepad update for safety - 60Hz"""
        while True:
            await asyncio.sleep(0.016)  # 60Hz
            self.gamepad.update()
    
    async def stats_loop(self):
        """Print performance stats"""
        while True:
            await asyncio.sleep(5)
            if self.start_time > 0:
                runtime = time.perf_counter() - self.start_time
                ori_rate = self.orientation_count / runtime if runtime > 0 else 0
                move_rate = self.move_count / runtime if runtime > 0 else 0
                print(f"📊 Stats: {runtime:.0f}s | Orientation: {ori_rate:.1f}Hz | Moves: {move_rate:.2f}Hz")
    
    async def keyboard_task(self):
        """Handle keyboard shortcuts"""
        # Set up keyboard hooks
        keyboard.add_hotkey('f5', self.calibrate)
        keyboard.add_hotkey('f6', self.reset_camera_joystick)
        
        print("⌨️  F5: Reset calibration | F6: Reset camera joystick")
        
        # Keep running to handle keyboard events
        while True:
            await asyncio.sleep(0.1)
    
    async def connect(self):
        """Simple connection"""
        self.cube = GanSmartCube()
        
        # Direct handlers - NO executor.submit()
        self.cube.on('orientation', self.handle_orientation)
        self.cube.on('move', self.handle_move)
        self.cube.on('battery', lambda e: print(f"Battery: {e.level}%"))
        
        await self.cube.connect()
        print("✅ Connected")
        self.start_time = time.perf_counter()
        
        # Auto-calibrate after 2 seconds
        await asyncio.sleep(2)
        if self.last_quaternion:
            self.calibrate()
            print("📍 Place cube with GREEN face forward")


async def main():
    controller = CubeControllerClean()
    
    try:
        await controller.connect()
        
        # Start background tasks
        update_task = asyncio.create_task(controller.update_loop())
        sprint_task = asyncio.create_task(controller.sprint_task())
        stats_task = asyncio.create_task(controller.stats_loop())
        keyboard_task = asyncio.create_task(controller.keyboard_task())
        
        print("\n✅ Ready! Move cube to control.")
        print("Press Ctrl+C to exit\n")
        
        # Just wait forever - no complex loops
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
