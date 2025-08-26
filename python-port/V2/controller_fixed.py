#!/usr/bin/env python3
"""
V2 Cube Controller - FIXED VERSION
Addresses feedback while fixing critical bugs from optimized version
"""

import asyncio
import time
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any
import threading
from concurrent.futures import ThreadPoolExecutor
import queue
import keyboard
import vgamepad as vg
import math

# Add parent directory to import gan_web_bluetooth
sys.path.append(str(Path(__file__).parent.parent))

# Use the existing, working GAN library
from gan_web_bluetooth import GanSmartCube
from gan_web_bluetooth.protocols.base import (
    GanCubeMoveEvent, 
    GanCubeOrientationEvent,
    GanCubeBatteryEvent,
    GanCubeHardwareEvent,
    GanCubeFaceletsEvent
)

# ============================================================================
# GAMEPAD WORKER WITH COMMAND QUEUE
# ============================================================================

class GamepadWorker:
    """Single worker thread for all gamepad operations"""
    
    def __init__(self):
        self.gamepad = vg.VX360Gamepad()
        self.command_queue = queue.Queue(maxsize=100)  # Limit queue size
        self.running = True
        
        # Atomic state for joystick
        self.joy_x = 0.0
        self.joy_y = 0.0
        self.joy_z = 0.0
        
        # Current button states
        self.buttons_held = set()
        
        # Start worker thread
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()
    
    def _worker(self):
        """Process commands and update gamepad at 250Hz"""
        last_update = time.perf_counter()
        
        while self.running:
            # Process pending commands (with timeout to avoid blocking)
            try:
                cmd, args = self.command_queue.get(timeout=0.001)
                self._execute_command(cmd, args)
            except queue.Empty:
                pass
            
            # Update gamepad at 250Hz
            now = time.perf_counter()
            if now - last_update >= 0.004:  # 250Hz
                self.gamepad.left_joystick_float(x_value_float=self.joy_x, y_value_float=self.joy_y)
                self.gamepad.right_joystick_float(x_value_float=self.joy_z, y_value_float=0)
                self.gamepad.update()
                last_update = now
    
    def _execute_command(self, cmd: str, args: tuple):
        """Execute a gamepad command"""
        if cmd == 'button_press':
            button, duration = args
            # Press immediately
            self.gamepad.press_button(button)
            self.gamepad.update()
            # Schedule release after duration
            def release():
                time.sleep(duration)
                self.queue_command('button_release', (button,))
            threading.Thread(target=release, daemon=True).start()
            
        elif cmd == 'button_release':
            button = args[0]
            self.gamepad.release_button(button)
            self.gamepad.update()
            self.buttons_held.discard(button)
            
        elif cmd == 'button_hold':
            button = args[0]
            self.gamepad.press_button(button)
            self.gamepad.update()
            self.buttons_held.add(button)
            
        elif cmd == 'combo':
            button1, button2, timing = args
            # Execute combo sequence in separate thread
            def do_combo():
                delay1, delay2, delay3, _ = timing
                
                if delay1 > 0:
                    time.sleep(delay1)
                
                # Press first button
                self.queue_command('button_hold', (button1,))
                time.sleep(delay2)
                
                # Press second button
                self.queue_command('button_hold', (button2,))
                time.sleep(delay3)
                
                # Release both
                self.queue_command('button_release', (button1,))
                self.queue_command('button_release', (button2,))
            
            threading.Thread(target=do_combo, daemon=True).start()
            
        elif cmd == 'trigger':
            side, duration = args
            if side == 'right':
                self.gamepad.right_trigger(255)
            else:
                self.gamepad.left_trigger(255)
            self.gamepad.update()
            
            # Schedule release
            def release():
                time.sleep(duration)
                self.queue_command('trigger_release', (side,))
            threading.Thread(target=release, daemon=True).start()
            
        elif cmd == 'trigger_release':
            side = args[0]
            if side == 'right':
                self.gamepad.right_trigger(0)
            else:
                self.gamepad.left_trigger(0)
            self.gamepad.update()
            
        elif cmd == 'reset':
            self.gamepad.reset()
            self.gamepad.update()
            self.buttons_held.clear()
            self.joy_x = 0
            self.joy_y = 0
            self.joy_z = 0
    
    def update_joystick(self, x: float, y: float, z: float):
        """Update joystick position atomically"""
        self.joy_x = max(-1.0, min(1.0, x))
        self.joy_y = max(-1.0, min(1.0, y))
        self.joy_z = max(-1.0, min(1.0, z))
    
    def queue_command(self, cmd: str, args: tuple):
        """Queue a command for the worker thread"""
        try:
            self.command_queue.put((cmd, args), block=False)
        except queue.Full:
            # Drop oldest command if queue is full
            try:
                self.command_queue.get_nowait()
                self.command_queue.put((cmd, args), block=False)
            except:
                pass
    
    def press_button(self, button, duration=0.1):
        """Queue button press"""
        self.queue_command('button_press', (button, duration))
    
    def hold_button(self, button):
        """Queue button hold"""
        self.queue_command('button_hold', (button,))
    
    def release_button(self, button):
        """Queue button release"""
        self.queue_command('button_release', (button,))
    
    def press_combo(self, button1, button2, timing=(0.0, 0.05, 0.1, 0.05)):
        """Queue button combo"""
        self.queue_command('combo', (button1, button2, timing))
    
    def press_trigger(self, side: str, duration=0.1):
        """Queue trigger press"""
        self.queue_command('trigger', (side, duration))
    
    def reset(self):
        """Queue reset"""
        self.queue_command('reset', ())
    
    def cleanup(self):
        """Cleanup worker thread"""
        self.running = False
        self.reset()


# ============================================================================
# ORIENTATION COALESCER
# ============================================================================

class OrientationCoalescer:
    """Coalesce orientation updates to reduce processing overhead"""
    
    def __init__(self, min_interval_ms: int = 8):  # 125Hz max
        self.min_interval_ms = min_interval_ms
        self.last_update_time = 0
    
    def should_process(self) -> bool:
        """Check if enough time has passed to process"""
        now_ms = time.perf_counter_ns() // 1_000_000
        if now_ms - self.last_update_time >= self.min_interval_ms:
            self.last_update_time = now_ms
            return True
        return False


# ============================================================================
# DUPLICATE FILTER
# ============================================================================

class DuplicateFilter:
    """Simple duplicate filter"""
    
    def __init__(self, window_ms: int = 50):
        self.window_ms = window_ms
        self.last_move = None
        self.last_move_time = 0
        self.lock = threading.Lock()  # Need lock since moves process in threads
    
    def is_duplicate(self, move: str) -> bool:
        """Check if move is duplicate"""
        with self.lock:
            now_ms = time.perf_counter_ns() // 1_000_000
            
            if move == self.last_move and (now_ms - self.last_move_time) < self.window_ms:
                return True
            
            self.last_move = move
            self.last_move_time = now_ms
            return False


# ============================================================================
# SIMPLIFIED SPRINT STATE MACHINE
# ============================================================================

class SimplifiedSprintMachine:
    """Simplified sprint/roll handling"""
    
    def __init__(self, gamepad: GamepadWorker):
        self.gamepad = gamepad
        self.sprinting = False
        self.forward_threshold = 0.7
        self.hysteresis = 0.1
    
    def update_orientation(self, pitch: float):
        """Update sprint based on pitch"""
        if not self.sprinting:
            should_sprint = pitch > self.forward_threshold
        else:
            should_sprint = pitch > (self.forward_threshold - self.hysteresis)
        
        if should_sprint != self.sprinting:
            self.sprinting = should_sprint
            if self.sprinting:
                self.gamepad.hold_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
                print("Sprint: ON")
            else:
                self.gamepad.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
                print("Sprint: OFF")
    
    def handle_roll(self):
        """Handle roll during sprint"""
        if not self.sprinting:
            return
        
        print("Rolling...")
        # Simple roll sequence via command queue
        self.gamepad.queue_command('button_release', (vg.XUSB_BUTTON.XUSB_GAMEPAD_B,))
        
        def restore():
            time.sleep(0.05)
            self.gamepad.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B, 0.1)
            time.sleep(0.15)
            if self.sprinting:
                self.gamepad.hold_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
        
        threading.Thread(target=restore, daemon=True).start()
    
    def stop(self):
        """Force stop sprint"""
        if self.sprinting:
            self.sprinting = False
            self.gamepad.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)


# ============================================================================
# FIXED CONTROLLER
# ============================================================================

class CubeControllerV2Fixed:
    """Fixed cube controller - balanced threading with proper event handling"""
    
    def __init__(self, config_path: str = "controller_config.json"):
        # Configuration
        self.config = self.load_config(config_path)
        
        # Cube connection
        self.cube: Optional[GanSmartCube] = None
        
        # Single gamepad worker
        self.gamepad = GamepadWorker()
        
        # Processors
        self.orientation_coalescer = OrientationCoalescer(min_interval_ms=8)
        self.duplicate_filter = DuplicateFilter(window_ms=50)
        self.sprint_machine = SimplifiedSprintMachine(self.gamepad)
        
        # State
        self.enable_sprint = True
        self.show_debug = True
        
        # Calibration
        self.calibration_reference = None
        self.last_raw_quaternion = None
        
        # Use 4 threads - balance between too few and too many
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # Stats
        self.orientation_count = 0
        self.move_count = 0
        self.coalesced_count = 0
        self.start_time = 0
        self.last_debug_time = 0
        
        # Setup hotkeys
        self._setup_hotkeys()
        
        print("V2 Cube Controller (FIXED) initialized")
        print(f"Using {self.executor._max_workers} worker threads for events")
        print(f"Single gamepad worker with command queue")
        print(f"Loaded {len(self.config.get('move_mappings', {}))} move mappings")
    
    def load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration"""
        paths_to_try = [
            Path(config_path),
            Path(__file__).parent / config_path,
            Path(__file__).parent / "config.json",
            Path(__file__).parent.parent / "controller_config.json"
        ]
        
        for path in paths_to_try:
            if path.exists():
                with open(path, 'r') as f:
                    config = json.load(f)
                    print(f"Loaded config from: {path}")
                    return config
        
        print("WARNING: No config file found, using defaults")
        return {"move_mappings": {}}
    
    async def connect_cube(self):
        """Connect to cube"""
        print("Connecting to cube...")
        
        self.cube = GanSmartCube()
        
        # Process both moves and orientation in thread pool to avoid blocking
        self.cube.on('move', lambda e: self.executor.submit(self.process_move, e))
        self.cube.on('orientation', lambda e: self.executor.submit(self.process_orientation, e))
        self.cube.on('battery', lambda e: print(f"Battery: {e.level}%"))
        self.cube.on('connected', self._handle_connected)
        self.cube.on('disconnected', lambda e: print("❌ Cube disconnected"))
        
        await self.cube.connect()
    
    def _handle_connected(self, event):
        """Handle connection"""
        print("✅ Cube connected!")
        self.start_time = time.perf_counter()
        
        # Auto-calibrate after 2 seconds
        def _calibrate():
            time.sleep(2)
            if self.last_raw_quaternion:
                print("\n🔄 Auto-calibrating...")
                self.calibrate()
                print("📍 Place cube with GREEN face forward\n")
        
        threading.Thread(target=_calibrate, daemon=True).start()
    
    def process_orientation(self, event: GanCubeOrientationEvent):
        """Process orientation with coalescing"""
        try:
            self.orientation_count += 1
            
            # Check if we should process (rate limit)
            if not self.orientation_coalescer.should_process():
                return
            
            self.coalesced_count += 1
            
            # Extract quaternion
            qx_raw = event.quaternion.x
            qy_raw = event.quaternion.y
            qz_raw = event.quaternion.z
            qw_raw = event.quaternion.w
            
            # Store for calibration
            self.last_raw_quaternion = {'x': qx_raw, 'y': qy_raw, 'z': qz_raw, 'w': qw_raw}
            
            # Apply calibration if available
            if self.calibration_reference:
                ref = self.calibration_reference
                
                # Normalize reference
                ref_norm = (ref['x']**2 + ref['y']**2 + ref['z']**2 + ref['w']**2) ** 0.5
                if ref_norm > 0:
                    ref_x = ref['x'] / ref_norm
                    ref_y = ref['y'] / ref_norm
                    ref_z = ref['z'] / ref_norm
                    ref_w = ref['w'] / ref_norm
                else:
                    ref_x, ref_y, ref_z, ref_w = 0, 0, 0, 1
                
                # Calculate relative rotation
                ref_inv_x = -ref_x
                ref_inv_y = -ref_y
                ref_inv_z = -ref_z
                ref_inv_w = ref_w
                
                qx = ref_inv_w*qx_raw + ref_inv_x*qw_raw + ref_inv_y*qz_raw - ref_inv_z*qy_raw
                qy = ref_inv_w*qy_raw - ref_inv_x*qz_raw + ref_inv_y*qw_raw + ref_inv_z*qx_raw
                qz = ref_inv_w*qz_raw + ref_inv_x*qy_raw - ref_inv_y*qx_raw + ref_inv_z*qw_raw
                qw = ref_inv_w*qw_raw - ref_inv_x*qx_raw - ref_inv_y*qy_raw - ref_inv_z*qz_raw
            else:
                qx, qy, qz, qw = qx_raw, qy_raw, qz_raw, qw_raw
            
            # Convert to joystick
            sensitivity = self.config.get('sensitivity', {})
            tilt_x_sens = sensitivity.get('tilt_x_sensitivity', 2.5)
            tilt_y_sens = sensitivity.get('tilt_y_sensitivity', 2.5)
            spin_z_sens = sensitivity.get('spin_z_sensitivity', 2.0)
            
            joy_y = -qx * tilt_y_sens * 2
            joy_x = qy * tilt_x_sens * 2
            joy_z = -qz * spin_z_sens
            
            # Apply deadzone
            deadzone = self.config.get('deadzone', {}).get('general_deadzone', 0.1)
            spin_deadzone = self.config.get('deadzone', {}).get('spin_deadzone', 0.085)
            
            if abs(joy_x) < deadzone: joy_x = 0
            if abs(joy_y) < deadzone: joy_y = 0
            if abs(joy_z) < spin_deadzone: joy_z = 0
            
            # Update joystick
            self.gamepad.update_joystick(joy_x, joy_y, joy_z)
            
            # Update sprint
            if self.enable_sprint:
                self.sprint_machine.update_orientation(joy_y)
            
            # Debug output
            if self.show_debug:
                now = time.perf_counter_ns() // 1_000_000
                if now - self.last_debug_time > 100:  # 10Hz
                    if abs(joy_x) > 0.1 or abs(joy_y) > 0.1 or abs(joy_z) > 0.1:
                        cal_str = "CAL" if self.calibration_reference else "RAW"
                        print(f"Joy: X={joy_x:5.2f} Y={joy_y:5.2f} Z={joy_z:5.2f} | {cal_str}")
                    self.last_debug_time = now
                    
        except Exception as e:
            print(f"Error processing orientation: {e}")
    
    def process_move(self, event: GanCubeMoveEvent):
        """Process move in worker thread"""
        try:
            move = event.move
            
            # Check duplicate
            if self.duplicate_filter.is_duplicate(move):
                return
            
            print(f"Move: {move}")
            self.move_count += 1
            
            # Special handling for roll during sprint
            if move == "U'" and self.sprint_machine.sprinting:
                self.sprint_machine.handle_roll()
                return
            
            # Get action from config
            action = self.config.get('move_mappings', {}).get(move)
            if not action:
                return
            
            # Execute action immediately
            self.execute_gamepad_action(action)
            
        except Exception as e:
            print(f"Error processing move: {e}")
    
    def execute_gamepad_action(self, action: str):
        """Execute gamepad action via command queue"""
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
        
        if action in button_map:
            self.gamepad.press_button(button_map[action])
            
        elif action == 'gamepad_r2':
            self.gamepad.press_trigger('right')
            
        elif action == 'gamepad_l2':
            self.gamepad.press_trigger('left')
            
        elif action.startswith('gamepad_combo_'):
            # Parse combo
            combo = action.replace('gamepad_combo_', '').split('+')
            if len(combo) == 2:
                button_map_combo = {
                    'y': vg.XUSB_BUTTON.XUSB_GAMEPAD_Y,
                    'dpad_down': vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN,
                    'dpad_up': vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP,
                    'dpad_left': vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT,
                    'dpad_right': vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT,
                    'r1': vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER,
                }
                
                button1 = button_map_combo.get(combo[0])
                button2 = button_map_combo.get(combo[1])
                
                if button1 and button2:
                    self.gamepad.press_combo(button1, button2)
    
    def calibrate(self):
        """Calibrate the cube"""
        if not self.last_raw_quaternion:
            print("ERROR: No cube data yet")
            return
        
        self.calibration_reference = self.last_raw_quaternion.copy()
        self.sprint_machine.stop()
        
        print(f"CALIBRATED: ({self.calibration_reference['x']:.3f}, "
              f"{self.calibration_reference['y']:.3f}, "
              f"{self.calibration_reference['z']:.3f}, "
              f"{self.calibration_reference['w']:.3f})")
    
    def _setup_hotkeys(self):
        """Setup keyboard hotkeys"""
        try:
            keyboard.add_hotkey('f5', lambda: self.calibrate())
            keyboard.add_hotkey('f6', self._toggle_sprint)
            keyboard.add_hotkey('f7', self._toggle_debug)
            keyboard.add_hotkey('f9', self._reset_joystick)
            
            print("\n📌 Hotkeys:")
            print("  F5 - Recalibrate")
            print("  F6 - Toggle sprint")
            print("  F7 - Toggle debug")
            print("  F9 - Reset joystick\n")
        except:
            pass
    
    def _toggle_sprint(self):
        self.enable_sprint = not self.enable_sprint
        print(f"Sprint: {'ON' if self.enable_sprint else 'OFF'}")
        if not self.enable_sprint:
            self.sprint_machine.stop()
    
    def _toggle_debug(self):
        self.show_debug = not self.show_debug
        print(f"Debug: {'ON' if self.show_debug else 'OFF'}")
    
    def _reset_joystick(self):
        print("Resetting...")
        self.sprint_machine.stop()
        self.gamepad.reset()
    
    async def print_stats_loop(self):
        """Print performance stats"""
        while True:
            await asyncio.sleep(5)
            
            if self.start_time > 0:
                runtime = time.perf_counter() - self.start_time
                if runtime > 0:
                    orientation_rate = self.orientation_count / runtime
                    coalesced_rate = self.coalesced_count / runtime
                    move_rate = self.move_count / runtime
                    
                    if self.orientation_count > 0:
                        drop_percent = ((1 - (self.coalesced_count / self.orientation_count)) * 100)
                    else:
                        drop_percent = 0
                    
                    print(f"\n📊 {runtime:.0f}s | Orient: {orientation_rate:.1f}Hz→{coalesced_rate:.1f}Hz ({drop_percent:.0f}% dropped) | Moves: {move_rate:.2f}Hz")
    
    async def run(self):
        """Main run loop"""
        try:
            await self.connect_cube()
            
            # Start stats printer
            stats_task = asyncio.create_task(self.print_stats_loop())
            
            print("\n✅ V2 FIXED ready!")
            print("Architecture: Single gamepad worker + 4 event processing threads")
            print("Orientation coalescing at 125Hz max")
            print("Move the cube to control\n")
            
            # Run forever
            await asyncio.Future()
            
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.gamepad.cleanup()
            self.executor.shutdown(wait=False)
            if self.cube:
                await self.cube.disconnect()
            try:
                keyboard.unhook_all()
            except:
                pass


# ============================================================================
# MAIN
# ============================================================================

async def main():
    controller = CubeControllerV2Fixed()
    await controller.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown complete")
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
"""
V2 Cube Controller - Direct BLE to Gamepad (Fixed Version)
Uses gan_web_bluetooth library for proper protocol handling
Focus: Remove WebSocket overhead, not reimplement BLE
"""

import asyncio
import time
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from collections import deque
import threading
import keyboard
import vgamepad as vg
import os

# Add parent directory to import gan_web_bluetooth
sys.path.append(str(Path(__file__).parent.parent))
KEYBOARD_AVAILABLE = True
GAMEPAD_AVAILABLE = True

# Use the existing, working GAN library
from gan_web_bluetooth import GanSmartCube
from gan_web_bluetooth.protocols.base import (
    GanCubeMoveEvent, 
    GanCubeOrientationEvent,
    GanCubeBatteryEvent,
    GanCubeHardwareEvent,
    GanCubeFaceletsEvent
)
from gan_web_bluetooth.utils import now
import math

# ============================================================================
# GAMEPAD BATCHER - Critical optimization from plan
# ============================================================================

class GamepadBatcher:
    """Batch gamepad updates to avoid calling update() too often"""
    
    def __init__(self, gamepad):
        self.gamepad = gamepad
        self.dirty = False
        self.buttons_pressed = set()
        self.buttons_released = set()
        
    def update_orientation(self, x: float, y: float, z: float):
        """Update joystick position (doesn't call update)"""
        # Clamp values
        x = max(-1.0, min(1.0, x))
        y = max(-1.0, min(1.0, y))
        z = max(-1.0, min(1.0, z))
        
        self.gamepad.left_joystick_float(x_value_float=x, y_value_float=y)
        self.gamepad.right_joystick_float(x_value_float=z, y_value_float=0)
        self.dirty = True
        
    def press_button(self, button):
        """Queue button press"""
        self.gamepad.press_button(button=button)
        self.buttons_pressed.add(button)
        self.buttons_released.discard(button)
        self.dirty = True
        
    def release_button(self, button):
        """Queue button release"""
        self.gamepad.release_button(button=button)
        self.buttons_released.add(button)
        self.buttons_pressed.discard(button)
        self.dirty = True
        
    def press_trigger(self, side: str, value: int = 255):
        """Press trigger"""
        if side == 'right':
            self.gamepad.right_trigger(value)
        else:
            self.gamepad.left_trigger(value)
        self.dirty = True
        
    async def flush_loop(self):
        """Background task that flushes updates at 125Hz"""
        while True:
            if self.dirty:
                self.gamepad.update()
                self.dirty = False
                self.buttons_pressed.clear()
                self.buttons_released.clear()
            await asyncio.sleep(0.008)  # 125Hz


# ============================================================================
# DUPLICATE FILTER
# ============================================================================

class DuplicateFilter:
    """Filter duplicate moves from cube"""
    
    def __init__(self):
        self.last_move = None
        self.last_move_time = 0
        
    def is_duplicate(self, move: str) -> bool:
        """Check if this move is a duplicate"""
        now_ms = time.perf_counter_ns() // 1_000_000
        
        # Same move within 50ms = duplicate
        if move == self.last_move and (now_ms - self.last_move_time) < 50: return True
        self.last_move = move
        self.last_move_time = now_ms
        return False


# ============================================================================
# SPRINT STATE MACHINE
# ============================================================================

class SprintStateMachine:
    """Handle sprint and roll mechanics"""
    
    def __init__(self, batcher: GamepadBatcher):
        self.batcher = batcher
        self.sprinting = False
        self.rolling = False
        self.forward_tilt_threshold = 0.7
        self.forward_tilt_hysteresis = 0.1  # Prevent jittering
        
    def update_orientation(self, pitch: float):
        """Update sprint state based on forward tilt with hysteresis"""
        # Use hysteresis to prevent jittering at threshold boundary
        if not self.sprinting:
            # Start sprint when above threshold
            should_sprint = pitch > self.forward_tilt_threshold
        else:
            # Stop sprint only when below threshold minus hysteresis
            should_sprint = pitch > (self.forward_tilt_threshold - self.forward_tilt_hysteresis)
        
        if should_sprint and not self.sprinting and not self.rolling:
            self.start_sprint()
        elif not should_sprint and self.sprinting and not self.rolling:
            self.stop_sprint()
            
    def start_sprint(self):
        """Start sprinting (hold B)"""
        self.sprinting = True
        self.batcher.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
        print("Sprint: ON")
        
    def stop_sprint(self):
        """Stop sprinting (release B)"""
        self.sprinting = False
        self.batcher.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
        print("Sprint: OFF")
        
    async def handle_roll(self):
        """Handle roll during sprint (U' move)"""
        if not self.sprinting or self.rolling:
            return
            
        self.rolling = True
        
        # Release B, tap B, re-hold B
        self.batcher.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
        await asyncio.sleep(0.05)
        
        self.batcher.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
        await asyncio.sleep(0.1)
        
        self.batcher.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
        await asyncio.sleep(0.05)
        
        if self.sprinting:  # Re-hold if still sprinting
            self.batcher.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
            
        self.rolling = False


# ============================================================================
# MAIN CONTROLLER
# ============================================================================

class CubeControllerV2:
    """Direct cube to gamepad controller using gan_web_bluetooth"""
    
    def __init__(self, config_path: str = "controller_config.json"):
        # Store config path for hot-reloading
        self.config_path = None
        self.config_last_modified = 0
        
        # Load configuration
        self.config = self.load_config(config_path)
        
        # Cube connection
        self.cube: Optional[GanSmartCube] = None
        
        # Gamepad
        self.gamepad = vg.VX360Gamepad()
        self.batcher = GamepadBatcher(self.gamepad)
        
        # Processors
        self.duplicate_filter = DuplicateFilter()
        self.sprint_machine = SprintStateMachine(self.batcher)
        
        # State tracking
        self.enable_sprint = True  # Sprint mode ENABLED
        self.last_orientation_time = 0
        self.last_orientation_debug = 0  # For debug output
        self.show_orientation_debug = True  # Toggle for orientation output
        
        # Calibration system from V1
        self.calibration_reference = None  # Will store raw quaternion when calibrated
        self.last_raw_quaternion = None  # Store last raw quaternion for calibration
        
        # Performance monitoring
        self.orientation_count = 0
        self.move_count = 0
        self.start_time = 0
        
        # Freeze detection (diagnostics only, no auto-disconnect)
        self.last_unique_quaternion = None
        self.same_quaternion_count = 0
        self.freeze_detected = False
        
        # Hotkey support
        self.hotkeys_registered = False
        
        print("V2 Cube Controller (Fixed) initialized")
        print(f"Loaded {len(self.config.get('move_mappings', {}))} move mappings")
        print(f"Sprint mode: {'ENABLED' if self.enable_sprint else 'DISABLED'} (threshold: {self.sprint_machine.forward_tilt_threshold})")
        
        # Setup hotkeys if available
        if KEYBOARD_AVAILABLE:
            self._setup_hotkeys()
        else:
            print("Hotkeys disabled (keyboard module not available)")
        
    def load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from JSON file"""
        paths_to_try = [
            Path(config_path),
            Path(__file__).parent / config_path,
            Path(__file__).parent / "config.json",
            Path(__file__).parent.parent / "controller_config.json"
        ]
        
        for path in paths_to_try:
            if path.exists():
                with open(path, 'r') as f:
                    config = json.load(f)
                    # Store the path and modification time for hot-reloading
                    self.config_path = path
                    self.config_last_modified = os.path.getmtime(path)
                    print(f"Loaded config from: {path}")
                    return config
                    
        print("WARNING: No config file found, using defaults")
        return {"move_mappings": {}}
        
    async def connect_cube(self):
        """Connect to cube using gan_web_bluetooth"""
        print("Connecting to cube...")
        
        # Create cube instance
        self.cube = GanSmartCube()
        
        # Setup event handlers
        self.cube.on('move', self._handle_move)
        self.cube.on('orientation', self._handle_orientation)
        self.cube.on('battery', self._handle_battery)
        self.cube.on('hardware', self._handle_hardware)
        self.cube.on('facelets', self._handle_facelets)
        self.cube.on('connected', self._handle_connected)
        self.cube.on('disconnected', self._handle_disconnected)
        
        # Connect (library handles protocol detection)
        await self.cube.connect()
        
    def _handle_connected(self, event):
        """Handle cube connected event"""
        print("✅ Cube connected successfully!")
        self.start_time = time.perf_counter()
        
        # Auto-calibrate after connection (like V1)
        asyncio.create_task(self._auto_calibrate())
        
    def _handle_disconnected(self, event):
        """Handle cube disconnected event"""
        print("❌ Cube disconnected")
        
    def _handle_move(self, event: GanCubeMoveEvent):
        """Handle move event - CRITICAL PATH"""
        move = event.move
        
        # Check for duplicate
        if self.duplicate_filter.is_duplicate(move):
            return
            
        print(f"Move: {move}")
        self.move_count += 1
        
        # Special handling for roll during sprint
        if move == "U'" and self.sprint_machine.sprinting:
            asyncio.create_task(self.sprint_machine.handle_roll())
            return
            
        # Get action from config
        action = self.config.get('move_mappings', {}).get(move)
        if not action:
            return
            
        # Execute action
        self._execute_gamepad_action(action)
        
    def _handle_orientation(self, event: GanCubeOrientationEvent):
        """Handle orientation event - CRITICAL PATH"""
        # No rate limiting here - process every event
        # The gamepad batcher already handles rate limiting at 125Hz
        now = time.perf_counter_ns() // 1_000_000
        self.last_orientation_time = now
        
        self.orientation_count += 1
        
        # Extract RAW quaternion
        qx_raw = event.quaternion.x
        qy_raw = event.quaternion.y
        qz_raw = event.quaternion.z
        qw_raw = event.quaternion.w
        
        # Store raw quaternion for calibration
        self.last_raw_quaternion = {'x': qx_raw, 'y': qy_raw, 'z': qz_raw, 'w': qw_raw}
        
        # Freeze detection - check if getting same exact values
        current_quat_rounded = (round(qx_raw, 4), round(qy_raw, 4), round(qz_raw, 4), round(qw_raw, 4))
        if current_quat_rounded == self.last_unique_quaternion:
            self.same_quaternion_count += 1
            
            # Warn if frozen for 2+ seconds (~20 updates at 10Hz)
            if self.same_quaternion_count == 20 and not self.freeze_detected:
                print(f"\n⚠️ WARNING: Orientation appears frozen! Same quaternion for 20+ updates")
                print(f"  Raw quaternion stuck at: {current_quat_rounded}")
                print("  Press F5 to recalibrate or F9 to reset joystick to center")
                self.freeze_detected = True
            elif self.same_quaternion_count % 50 == 0:  # Remind every 5 seconds
                print(f"  Still frozen ({self.same_quaternion_count} identical updates)")
        else:
            # Values changed
            if self.freeze_detected:
                print(f"✅ Orientation unfrozen after {self.same_quaternion_count} updates")
                self.freeze_detected = False
            self.same_quaternion_count = 0
            self.last_unique_quaternion = current_quat_rounded
        
        # Apply calibration if available (same as V1)
        if self.calibration_reference:
            # Calculate relative rotation from calibration reference
            ref = self.calibration_reference
            
            # Normalize reference quaternion
            ref_norm = (ref['x']**2 + ref['y']**2 + ref['z']**2 + ref['w']**2) ** 0.5
            if ref_norm > 0:
                ref_x = ref['x'] / ref_norm
                ref_y = ref['y'] / ref_norm
                ref_z = ref['z'] / ref_norm
                ref_w = ref['w'] / ref_norm
            else:
                ref_x, ref_y, ref_z, ref_w = 0, 0, 0, 1
            
            # Calculate inverse (conjugate) of reference quaternion
            ref_inv_x = -ref_x
            ref_inv_y = -ref_y
            ref_inv_z = -ref_z
            ref_inv_w = ref_w
            
            # Calculate relative rotation: relative = inverse(reference) * current
            qx = ref_inv_w*qx_raw + ref_inv_x*qw_raw + ref_inv_y*qz_raw - ref_inv_z*qy_raw
            qy = ref_inv_w*qy_raw - ref_inv_x*qz_raw + ref_inv_y*qw_raw + ref_inv_z*qx_raw
            qz = ref_inv_w*qz_raw + ref_inv_x*qy_raw - ref_inv_y*qx_raw + ref_inv_z*qw_raw
            qw = ref_inv_w*qw_raw - ref_inv_x*qx_raw - ref_inv_y*qy_raw - ref_inv_z*qz_raw
        else:
            # No calibration - use raw
            qx, qy, qz, qw = qx_raw, qy_raw, qz_raw, qw_raw
        
        # Use V1's direct quaternion component mapping (more intuitive)
        # When calibrated, identity quaternion (0,0,0,1) = cube at rest
        # The calibrated quaternion components directly map to tilt
        
        # Get sensitivity settings (use V1 names)
        sensitivity = self.config.get('sensitivity', {})
        tilt_x_sens = sensitivity.get('tilt_x_sensitivity', 2.5)
        tilt_y_sens = sensitivity.get('tilt_y_sensitivity', 2.5) 
        spin_z_sens = sensitivity.get('spin_z_sensitivity', 2.0)
        
        # V1 mapping: quaternion components directly control joysticks
        # INVERTED for intuitive control (like V1)
        joy_y = -qx * tilt_y_sens * 2   # Forward/back tilt (INVERTED)
        joy_x = qy * tilt_x_sens * 2    # Left/right tilt
        joy_z = -qz * spin_z_sens       # Rotation around vertical
        
        # Clamp to valid range
        joy_x = max(-1.0, min(1.0, joy_x))
        joy_y = max(-1.0, min(1.0, joy_y))
        joy_z = max(-1.0, min(1.0, joy_z))
        
        # Apply deadzone
        deadzone = self.config.get('deadzone', {}).get('general_deadzone', 0.1)
        spin_deadzone = self.config.get('deadzone', {}).get('spin_deadzone', 0.085)
        
        if abs(joy_x) < deadzone:
            joy_x = 0
        if abs(joy_y) < deadzone:
            joy_y = 0
        if abs(joy_z) < spin_deadzone:
            joy_z = 0
            
        # Update gamepad through batcher
        self.batcher.update_orientation(joy_x, joy_y, joy_z)
        
        # Debug output (rate limited to avoid spam)
        if self.show_orientation_debug and now - self.last_orientation_debug > 100: # 100ms updates for now
            # Always show output if values are significant OR if we haven't printed in a while
            time_since_last = now - self.last_orientation_debug
            if abs(joy_x) > 0.1 or abs(joy_y) > 0.1 or abs(joy_z) > 0.1 or time_since_last > 2000:
                if self.calibration_reference:
                    print(f"Joystick: X={joy_x:.2f} Y={joy_y:.2f} Z={joy_z:.2f} | Calibrated: ({qx:.3f}, {qy:.3f}, {qz:.3f}, {qw:.3f})")
                else:
                    print(f"Joystick: X={joy_x:.2f} Y={joy_y:.2f} Z={joy_z:.2f} | RAW (not calibrated): ({qx:.3f}, {qy:.3f}, {qz:.3f}, {qw:.3f})")
                
                # If values are near zero but we're still getting updates, note that
                if abs(joy_x) <= 0.1 and abs(joy_y) <= 0.1 and abs(joy_z) <= 0.1 and time_since_last > 2000:
                    print(f"  (Near-zero values for {time_since_last/1000:.1f}s)")
            
            self.last_orientation_debug = now
        
        # Update sprint state if enabled
        if self.enable_sprint:
            # Use forward tilt (joy_y) for sprint detection
            self.sprint_machine.update_orientation(joy_y)
        
    def _handle_battery(self, event: GanCubeBatteryEvent):
        """Handle battery event"""
        print(f"Battery: {event.level}%")
        
    def _handle_hardware(self, event: GanCubeHardwareEvent):
        """Handle hardware info event"""
        # Usually just logged once at connection
        pass
        
    def _handle_facelets(self, event: GanCubeFaceletsEvent):
        """Handle cube state update"""
        # Not needed for gamepad control
        pass
        
    def _execute_gamepad_action(self, action: str):
        """Execute gamepad action through batcher"""
        # Button mappings
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
        
        if action in button_map:
            button = button_map[action]
            self.batcher.press_button(button)
            asyncio.create_task(self._delayed_release(button, 0.1))
            
        elif action == 'gamepad_r2':
            self.batcher.press_trigger('right', 255)
            asyncio.create_task(self._delayed_trigger_release('right', 0.1))
            
        elif action == 'gamepad_l2':
            self.batcher.press_trigger('left', 255)
            asyncio.create_task(self._delayed_trigger_release('left', 0.1))
            
        elif action.startswith('gamepad_combo_'):
            asyncio.create_task(self._execute_combo(action))
            
        elif action == 'gamepad_b_hold':
            # Sprint mode auto-hold
            self.sprint_machine.start_sprint()
            
        elif action == 'gamepad_b_release':
            # Sprint mode auto-release
            self.sprint_machine.stop_sprint()
            
    async def _delayed_release(self, button, delay: float):
        """Release button after delay"""
        await asyncio.sleep(delay)
        self.batcher.release_button(button)
        
    async def _delayed_trigger_release(self, side: str, delay: float):
        """Release trigger after delay"""
        await asyncio.sleep(delay)
        self.batcher.press_trigger(side, 0)
        
    async def _execute_combo(self, action: str):
        """Execute button combo"""
        # Parse combo (e.g., gamepad_combo_y+dpad_down)
        combo = action.replace('gamepad_combo_', '').split('+')
        if len(combo) != 2:
            return
            
        button_map = {
            'y': vg.XUSB_BUTTON.XUSB_GAMEPAD_Y,
            'dpad_down': vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN,
            'r1': vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER,
        }
        
        button1 = button_map.get(combo[0])
        button2 = button_map.get(combo[1])
        
        if button1 and button2:
            self.batcher.press_button(button1)
            await asyncio.sleep(0.05)
            self.batcher.press_button(button2)
            await asyncio.sleep(0.1)
            self.batcher.release_button(button2)
            await asyncio.sleep(0.05)
            self.batcher.release_button(button1)
            
    async def _auto_calibrate(self):
        """Auto-calibrate after connection (same as V1)"""
        # Wait for orientation data to start flowing
        await asyncio.sleep(2.0)
        
        if self.last_raw_quaternion:
            print("\n🔄 Auto-calibrating cube...")
            self.calibrate()
            print("📍 Place cube with GREEN face forward for optimal control\n")
        else:
            print("⚠️ No orientation data yet, skipping auto-calibration")
    
    def _setup_hotkeys(self):
        """Setup keyboard hotkeys for various functions"""
        try:
            # F5 for recalibration
            keyboard.add_hotkey('f5', self._hotkey_recalibrate, suppress=False)
            
            # F6 to toggle sprint mode
            keyboard.add_hotkey('f6', self._hotkey_toggle_sprint, suppress=False)
            
            # F7 to toggle debug output
            keyboard.add_hotkey('f7', self._hotkey_toggle_debug, suppress=False)
            
            # F8 to reload config
            keyboard.add_hotkey('f8', self._hotkey_reload_config, suppress=False)
            
            # F9 to reset joystick
            keyboard.add_hotkey('f9', self._hotkey_reset_joystick, suppress=False)
            
            self.hotkeys_registered = True
            print("\n📌 Hotkeys enabled:")
            print("  F5 - Recalibrate cube")
            print("  F6 - Toggle sprint mode")
            print("  F7 - Toggle debug output")
            print("  F8 - Reload config")
            print("  F9 - Reset joystick to center\n")
            
        except Exception as e:
            print(f"Failed to register hotkeys: {e}")
            self.hotkeys_registered = False
    
    def _hotkey_recalibrate(self):
        """Hotkey handler for recalibration (thread-safe)"""
        # Schedule the calibration in the async event loop
        if self.last_raw_quaternion:
            print("\n🔄 [F5] Recalibrating cube...")
            self.calibrate()
        else:
            print("\n⚠️ [F5] Cannot calibrate - no orientation data yet")
    
    def _hotkey_toggle_sprint(self):
        """Hotkey handler to toggle sprint mode"""
        self.enable_sprint = not self.enable_sprint
        status = "ENABLED" if self.enable_sprint else "DISABLED"
        print(f"\n🏃 [F6] Sprint mode: {status}")
        
        # If disabling sprint while sprinting, stop it
        if not self.enable_sprint and self.sprint_machine.sprinting:
            self.sprint_machine.stop_sprint()
    
    def _hotkey_toggle_debug(self):
        """Hotkey handler to toggle debug output"""
        self.show_orientation_debug = not self.show_orientation_debug
        status = "ON" if self.show_orientation_debug else "OFF"
        print(f"\n🐛 [F7] Debug output: {status}")
    
    def _hotkey_reload_config(self):
        """Hotkey handler to reload config"""
        self.reload_config()
    
    def _hotkey_reset_joystick(self):
        """Hotkey handler to reset joystick to center (emergency stop)"""
        print("\n🎮 [F9] Resetting joystick to center...")
        
        # Stop any sprint
        if self.sprint_machine.sprinting:
            self.sprint_machine.stop_sprint()
        
        # Reset joystick to center
        self.batcher.update_orientation(0, 0, 0)
        
        # Clear freeze detection
        self.freeze_detected = False
        self.same_quaternion_count = 0
        
        print("  Joystick centered. Try moving the cube to resume control.")
    
    def reload_config(self):
        """Reload configuration from file"""
        if not self.config_path:
            print("\n⚠️ No config file to reload")
            return
            
        try:
            with open(self.config_path, 'r') as f:
                new_config = json.load(f)
            
            # Update config
            self.config = new_config
            self.config_last_modified = os.path.getmtime(self.config_path)
            
            # Update sprint threshold if changed
            if 'timing' in new_config:
                new_threshold = new_config['timing'].get('forward_tilt_threshold', 0.7)
                if new_threshold != self.sprint_machine.forward_tilt_threshold:
                    self.sprint_machine.forward_tilt_threshold = new_threshold
                    print(f"  Sprint threshold updated: {new_threshold}")
            
            print(f"\n♻️ [F8] Config reloaded from {self.config_path.name}")
            print(f"  {len(self.config.get('move_mappings', {}))} move mappings loaded")
            
        except Exception as e:
            print(f"\n❌ Failed to reload config: {e}")
    
    def calibrate(self):
        """Calibrate the cube to current position (same as V1)"""
        if not self.last_raw_quaternion:
            print("ERROR: No cube data yet. Move the cube first.")
            return
            
        # Store current RAW quaternion as calibration reference
        self.calibration_reference = self.last_raw_quaternion.copy()
        
        # Reset sprint state on calibration
        if self.sprint_machine.sprinting:
            self.sprint_machine.stop_sprint()
        
        print(f"CALIBRATION: Reference = ({self.calibration_reference['x']:.3f}, "
              f"{self.calibration_reference['y']:.3f}, {self.calibration_reference['z']:.3f}, "
              f"{self.calibration_reference['w']:.3f})")
        print("Cube calibrated! Current position is now identity (0,0,0,1)")
    
    async def print_stats_loop(self):
        """Print performance statistics and check for config changes"""
        last_check_time = time.time()
        
        while True:
            await asyncio.sleep(5)
            
            if self.start_time > 0:
                runtime = time.perf_counter() - self.start_time
                orientation_rate = self.orientation_count / runtime if runtime > 0 else 0
                move_rate = self.move_count / runtime if runtime > 0 else 0
                
                print(f"\n📊 Stats: {runtime:.0f}s | Orientation: {orientation_rate:.1f}Hz | Moves: {move_rate:.2f}Hz")
            
            # Check for config file changes (every 5 seconds)
            now = time.time()
            if self.config_path and now - last_check_time > 5:
                try:
                    current_mtime = os.path.getmtime(self.config_path)
                    if current_mtime > self.config_last_modified:
                        print("\n🔄 Config file changed, auto-reloading...")
                        self.reload_config()
                except:
                    pass  # File might be temporarily unavailable during save
                last_check_time = now
                
    async def run(self):
        """Main run loop"""
        try:
            # Connect to cube
            await self.connect_cube()
            
            # Start background tasks
            flush_task = asyncio.create_task(self.batcher.flush_loop())
            stats_task = asyncio.create_task(self.print_stats_loop())
            
            print("\n✅ V2 Controller ready!")
            print("Move the cube to control gamepad.")
            print("Press Ctrl+C to exit.\n")
            
            # Run forever
            await asyncio.Future()
            
        except KeyboardInterrupt:
            print("\nShutting down...")
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Cleanup
            if self.cube:
                await self.cube.disconnect()
            self.gamepad.reset()
            self.gamepad.update()
            
            # Cleanup hotkeys
            if KEYBOARD_AVAILABLE and self.hotkeys_registered:
                try:
                    keyboard.unhook_all()
                    print("Hotkeys unregistered")
                except:
                    pass


# ============================================================================
# MAIN
# ============================================================================

async def main():
    controller = CubeControllerV2()
    await controller.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown complete")
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
