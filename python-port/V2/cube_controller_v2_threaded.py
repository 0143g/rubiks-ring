#!/usr/bin/env python3
"""
V2 Cube Controller - MULTI-THREADED VERSION
Uses real threads for true parallelism, fixes combo timing
"""

import asyncio
import time
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from collections import deque
import threading
from concurrent.futures import ThreadPoolExecutor
import queue
import keyboard
import vgamepad as vg
import os
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
# THREAD-SAFE GAMEPAD CONTROLLER
# ============================================================================

class ThreadSafeGamepad:
    """Thread-safe gamepad wrapper with immediate updates"""
    
    def __init__(self):
        self.gamepad = vg.VX360Gamepad()
        self.lock = threading.Lock()
        
        # Current joystick state
        self.joy_x = 0.0
        self.joy_y = 0.0
        self.joy_z = 0.0
        
        # Start update thread
        self.running = True
        self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self.update_thread.start()
    
    def _update_loop(self):
        """Dedicated thread for gamepad updates at 250Hz"""
        while self.running:
            with self.lock:
                # Update gamepad state
                self.gamepad.left_joystick_float(x_value_float=self.joy_x, y_value_float=self.joy_y)
                self.gamepad.right_joystick_float(x_value_float=self.joy_z, y_value_float=0)
                self.gamepad.update()
            
            time.sleep(0.004)  # 250Hz
    
    def update_joystick(self, x: float, y: float, z: float):
        """Update joystick position (thread-safe)"""
        x = max(-1.0, min(1.0, x))
        y = max(-1.0, min(1.0, y))
        z = max(-1.0, min(1.0, z))
        
        with self.lock:
            self.joy_x = x
            self.joy_y = y
            self.joy_z = z
    
    def press_button(self, button, duration=0.1):
        """Press and release button (thread-safe)"""
        def _press():
            with self.lock:
                self.gamepad.press_button(button)
                self.gamepad.update()
            time.sleep(duration)
            with self.lock:
                self.gamepad.release_button(button)
                self.gamepad.update()
        
        # Run in separate thread to not block
        threading.Thread(target=_press, daemon=True).start()
    
    def press_combo(self, button1, button2, timing=(0.0, 0.05, 0.1, 0.05)):
        """Execute button combo with precise timing"""
        def _combo():
            delay1, delay2, delay3, delay4 = timing
            
            if delay1 > 0:
                time.sleep(delay1)
            
            # Press first button
            with self.lock:
                self.gamepad.press_button(button1)
                self.gamepad.update()
            
            time.sleep(delay2)
            
            # Press second button (while first is held)
            with self.lock:
                self.gamepad.press_button(button2)
                self.gamepad.update()
            
            time.sleep(delay3)
            
            # Release both
            with self.lock:
                self.gamepad.release_button(button2)
                self.gamepad.release_button(button1)
                self.gamepad.update()
        
        # Run combo in separate thread
        threading.Thread(target=_combo, daemon=True).start()
    
    def press_trigger(self, side: str, duration=0.1):
        """Press trigger"""
        def _trigger():
            with self.lock:
                if side == 'right':
                    self.gamepad.right_trigger(255)
                else:
                    self.gamepad.left_trigger(255)
                self.gamepad.update()
            
            time.sleep(duration)
            
            with self.lock:
                if side == 'right':
                    self.gamepad.right_trigger(0)
                else:
                    self.gamepad.left_trigger(0)
                self.gamepad.update()
        
        threading.Thread(target=_trigger, daemon=True).start()
    
    def hold_button(self, button):
        """Hold button down"""
        with self.lock:
            self.gamepad.press_button(button)
            self.gamepad.update()
    
    def release_button(self, button):
        """Release button"""
        with self.lock:
            self.gamepad.release_button(button)
            self.gamepad.update()
    
    def reset(self):
        """Reset gamepad to neutral"""
        with self.lock:
            self.joy_x = 0
            self.joy_y = 0
            self.joy_z = 0
            self.gamepad.reset()
            self.gamepad.update()
    
    def cleanup(self):
        """Cleanup gamepad"""
        self.running = False
        self.reset()


# ============================================================================
# DUPLICATE FILTER
# ============================================================================

class DuplicateFilter:
    """Thread-safe duplicate filter"""
    
    def __init__(self):
        self.last_move = None
        self.last_move_time = 0
        self.lock = threading.Lock()
    
    def is_duplicate(self, move: str) -> bool:
        """Check if this move is a duplicate"""
        with self.lock:
            now_ms = time.perf_counter_ns() // 1_000_000
            
            if move == self.last_move and (now_ms - self.last_move_time) < 50:
                return True
            
            self.last_move = move
            self.last_move_time = now_ms
            return False


# ============================================================================
# SPRINT STATE MACHINE (Thread-Safe)
# ============================================================================

class SprintStateMachine:
    """Handle sprint and roll mechanics"""
    
    def __init__(self, gamepad: ThreadSafeGamepad):
        self.gamepad = gamepad
        self.sprinting = False
        self.rolling = False
        self.forward_tilt_threshold = 0.7
        self.forward_tilt_hysteresis = 0.1
        self.lock = threading.Lock()
    
    def update_orientation(self, pitch: float):
        """Update sprint state based on forward tilt"""
        with self.lock:
            if not self.sprinting:
                should_sprint = pitch > self.forward_tilt_threshold
            else:
                should_sprint = pitch > (self.forward_tilt_threshold - self.forward_tilt_hysteresis)
            
            if should_sprint and not self.sprinting and not self.rolling:
                self.start_sprint()
            elif not should_sprint and self.sprinting and not self.rolling:
                self.stop_sprint()
    
    def start_sprint(self):
        """Start sprinting (hold B)"""
        self.sprinting = True
        self.gamepad.hold_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
        print("Sprint: ON")
    
    def stop_sprint(self):
        """Stop sprinting (release B)"""
        self.sprinting = False
        self.gamepad.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
        print("Sprint: OFF")
    
    def handle_roll(self):
        """Handle roll during sprint (U' move)"""
        if not self.sprinting or self.rolling:
            return
        
        def _roll():
            with self.lock:
                self.rolling = True
            
            # Roll sequence
            self.gamepad.release_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
            time.sleep(0.05)
            self.gamepad.press_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B, duration=0.1)
            time.sleep(0.05)
            
            with self.lock:
                if self.sprinting:
                    self.gamepad.hold_button(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
                self.rolling = False
        
        threading.Thread(target=_roll, daemon=True).start()


# ============================================================================
# MULTI-THREADED CONTROLLER
# ============================================================================

class CubeControllerV2Threaded:
    """Multi-threaded cube controller for maximum performance"""
    
    def __init__(self, config_path: str = "controller_config.json"):
        # Configuration
        self.config_path = None
        self.config = self.load_config(config_path)
        
        # Cube connection
        self.cube: Optional[GanSmartCube] = None
        
        # Thread-safe gamepad
        self.gamepad = ThreadSafeGamepad()
        
        # Processors
        self.duplicate_filter = DuplicateFilter()
        self.sprint_machine = SprintStateMachine(self.gamepad)
        
        # State
        self.enable_sprint = True
        self.show_debug = True
        
        # Calibration
        self.calibration_reference = None
        self.last_raw_quaternion = None
        self.calibration_lock = threading.Lock()
        
        # Thread pool for parallel processing
        self.executor = ThreadPoolExecutor(max_workers=8)  # Use 8 threads as requested
        
        # Performance monitoring
        self.orientation_count = 0
        self.move_count = 0
        self.start_time = 0
        self.last_debug_time = 0
        
        # Setup hotkeys
        self._setup_hotkeys()
        
        print("V2 Cube Controller (MULTI-THREADED) initialized")
        print(f"Using {self.executor._max_workers} worker threads")
        print(f"Loaded {len(self.config.get('move_mappings', {}))} move mappings")
        print(f"Sprint mode: {'ENABLED' if self.enable_sprint else 'DISABLED'}")
    
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
                    self.config_path = path
                    print(f"Loaded config from: {path}")
                    return config
        
        print("WARNING: No config file found, using defaults")
        return {"move_mappings": {}}
    
    async def connect_cube(self):
        """Connect to cube"""
        print("Connecting to cube...")
        
        self.cube = GanSmartCube()
        
        # Setup event handlers - process in thread pool
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
        """Process orientation in worker thread"""
        try:
            self.orientation_count += 1
            
            # Extract quaternion
            qx_raw = event.quaternion.x
            qy_raw = event.quaternion.y
            qz_raw = event.quaternion.z
            qw_raw = event.quaternion.w
            
            # Store for calibration
            with self.calibration_lock:
                self.last_raw_quaternion = {'x': qx_raw, 'y': qy_raw, 'z': qz_raw, 'w': qw_raw}
                
                # Apply calibration
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
            
            # Convert to joystick (fast path)
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
            
            # Update gamepad immediately
            self.gamepad.update_joystick(joy_x, joy_y, joy_z)
            
            # Update sprint
            if self.enable_sprint:
                self.sprint_machine.update_orientation(joy_y)
            
            # Debug output (rate limited)
            if self.show_debug:
                now = time.perf_counter_ns() // 1_000_000
                if now - self.last_debug_time > 100:  # 10Hz debug
                    if abs(joy_x) > 0.1 or abs(joy_y) > 0.1 or abs(joy_z) > 0.1:
                        cal_str = "Calibrated" if self.calibration_reference else "RAW"
                        print(f"Joy: X={joy_x:5.2f} Y={joy_y:5.2f} Z={joy_z:5.2f} | {cal_str}")
                    self.last_debug_time = now
                    
        except Exception as e:
            print(f"Error processing orientation: {e}")
    
    def process_move(self, event: GanCubeMoveEvent):
        """Process move in worker thread - IMMEDIATE execution for combos"""
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
            
            # Execute gamepad action IMMEDIATELY
            self.execute_gamepad_action(action)
            
        except Exception as e:
            print(f"Error processing move: {e}")
    
    def execute_gamepad_action(self, action: str):
        """Execute gamepad action with proper timing for combos"""
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
            self.gamepad.press_button(button)
            
        elif action == 'gamepad_r2':
            self.gamepad.press_trigger('right')
            
        elif action == 'gamepad_l2':
            self.gamepad.press_trigger('left')
            
        elif action.startswith('gamepad_combo_'):
            # Parse combo (e.g., gamepad_combo_y+dpad_down)
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
                    # Execute combo with proper timing
                    self.gamepad.press_combo(button1, button2)
    
    def calibrate(self):
        """Calibrate the cube"""
        with self.calibration_lock:
            if not self.last_raw_quaternion:
                print("ERROR: No cube data yet")
                return
            
            self.calibration_reference = self.last_raw_quaternion.copy()
            
            if self.sprint_machine.sprinting:
                self.sprint_machine.stop_sprint()
            
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
        if not self.enable_sprint and self.sprint_machine.sprinting:
            self.sprint_machine.stop_sprint()
    
    def _toggle_debug(self):
        self.show_debug = not self.show_debug
        print(f"Debug: {'ON' if self.show_debug else 'OFF'}")
    
    def _reset_joystick(self):
        print("Resetting joystick...")
        if self.sprint_machine.sprinting:
            self.sprint_machine.stop_sprint()
        self.gamepad.reset()
    
    async def print_stats_loop(self):
        """Print stats"""
        while True:
            await asyncio.sleep(5)
            
            if self.start_time > 0:
                runtime = time.perf_counter() - self.start_time
                orientation_rate = self.orientation_count / runtime if runtime > 0 else 0
                move_rate = self.move_count / runtime if runtime > 0 else 0
                
                # Get thread pool stats
                active = self.executor._threads.__len__()
                
                print(f"\n📊 {runtime:.0f}s | Orient: {orientation_rate:.1f}Hz | Moves: {move_rate:.2f}Hz | Threads: {active}/8")
    
    async def run(self):
        """Main run loop"""
        try:
            await self.connect_cube()
            
            # Start stats printer
            stats_task = asyncio.create_task(self.print_stats_loop())
            
            print("\n✅ V2 THREADED ready!")
            print("Using 8 parallel threads for processing")
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
    controller = CubeControllerV2Threaded()
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