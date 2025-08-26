#!/usr/bin/env python3
"""
V2 Cube Controller - ASYNC VERSION
Fixes freezing by using async queues to decouple BLE from processing
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
import math

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
        if move == self.last_move and (now_ms - self.last_move_time) < 50:
            return True
            
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
# ASYNC CONTROLLER WITH QUEUES
# ============================================================================

class CubeControllerV2Async:
    """Async cube controller with non-blocking event processing"""
    
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
        self.enable_sprint = True
        self.show_orientation_debug = True
        
        # Calibration system
        self.calibration_reference = None
        self.last_raw_quaternion = None
        
        # ASYNC QUEUES - The key to non-blocking!
        self.orientation_queue = asyncio.Queue(maxsize=100)
        self.move_queue = asyncio.Queue(maxsize=100)
        
        # Performance monitoring
        self.orientation_count = 0
        self.move_count = 0
        self.start_time = 0
        self.last_orientation_debug = 0
        
        # Hotkey support
        self.hotkeys_registered = False
        
        print("V2 Cube Controller (ASYNC) initialized")
        print(f"Loaded {len(self.config.get('move_mappings', {}))} move mappings")
        print(f"Sprint mode: {'ENABLED' if self.enable_sprint else 'DISABLED'}")
        
        # Setup hotkeys if available
        if KEYBOARD_AVAILABLE:
            self._setup_hotkeys()
    
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
        
        # Setup event handlers - MINIMAL WORK IN HANDLERS!
        self.cube.on('move', self._handle_move_minimal)
        self.cube.on('orientation', self._handle_orientation_minimal)
        self.cube.on('battery', self._handle_battery)
        self.cube.on('hardware', self._handle_hardware)
        self.cube.on('facelets', self._handle_facelets)
        self.cube.on('connected', self._handle_connected)
        self.cube.on('disconnected', self._handle_disconnected)
        
        # Connect
        await self.cube.connect()
    
    def _handle_connected(self, event):
        """Handle cube connected event"""
        print("✅ Cube connected successfully!")
        self.start_time = time.perf_counter()
        
        # Auto-calibrate after connection
        asyncio.create_task(self._auto_calibrate())
    
    def _handle_disconnected(self, event):
        """Handle cube disconnected event"""
        print("❌ Cube disconnected")
    
    # =========================================================================
    # MINIMAL EVENT HANDLERS - Just queue the data!
    # =========================================================================
    
    def _handle_move_minimal(self, event: GanCubeMoveEvent):
        """MINIMAL handler - just queue the move"""
        try:
            self.move_queue.put_nowait(event)
        except asyncio.QueueFull:
            # Drop oldest move if queue is full
            try:
                self.move_queue.get_nowait()
                self.move_queue.put_nowait(event)
            except:
                pass
    
    def _handle_orientation_minimal(self, event: GanCubeOrientationEvent):
        """MINIMAL handler - just queue the orientation"""
        try:
            self.orientation_queue.put_nowait(event)
        except asyncio.QueueFull:
            # Drop oldest orientation if queue is full
            try:
                self.orientation_queue.get_nowait()
                self.orientation_queue.put_nowait(event)
            except:
                pass
    
    def _handle_battery(self, event: GanCubeBatteryEvent):
        """Handle battery event"""
        print(f"Battery: {event.level}%")
    
    def _handle_hardware(self, event: GanCubeHardwareEvent):
        """Handle hardware info event"""
        pass
    
    def _handle_facelets(self, event: GanCubeFaceletsEvent):
        """Handle cube state update"""
        pass
    
    # =========================================================================
    # ASYNC PROCESSORS - Do the heavy work here!
    # =========================================================================
    
    async def process_orientation_queue(self):
        """Process orientation events from queue asynchronously"""
        while True:
            try:
                event = await self.orientation_queue.get()
                
                # Process the orientation
                await self._process_orientation(event)
                
            except Exception as e:
                print(f"Error processing orientation: {e}")
                await asyncio.sleep(0.001)
    
    async def process_move_queue(self):
        """Process move events from queue asynchronously"""
        while True:
            try:
                event = await self.move_queue.get()
                
                # Process the move
                await self._process_move(event)
                
            except Exception as e:
                print(f"Error processing move: {e}")
                await asyncio.sleep(0.001)
    
    async def _process_orientation(self, event: GanCubeOrientationEvent):
        """Process orientation event (async, non-blocking)"""
        self.orientation_count += 1
        now = time.perf_counter_ns() // 1_000_000
        
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
            
            # Calculate inverse of reference
            ref_inv_x = -ref_x
            ref_inv_y = -ref_y
            ref_inv_z = -ref_z
            ref_inv_w = ref_w
            
            # Calculate relative rotation
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
        
        if abs(joy_x) < deadzone:
            joy_x = 0
        if abs(joy_y) < deadzone:
            joy_y = 0
        if abs(joy_z) < spin_deadzone:
            joy_z = 0
        
        # Update gamepad
        self.batcher.update_orientation(joy_x, joy_y, joy_z)
        
        # Update sprint
        if self.enable_sprint:
            self.sprint_machine.update_orientation(joy_y)
        
        # Debug output
        if self.show_orientation_debug and now - self.last_orientation_debug > 100:
            if abs(joy_x) > 0.1 or abs(joy_y) > 0.1 or abs(joy_z) > 0.1:
                if self.calibration_reference:
                    print(f"Joystick: X={joy_x:.2f} Y={joy_y:.2f} Z={joy_z:.2f} | Calibrated: ({qx:.3f}, {qy:.3f}, {qz:.3f}, {qw:.3f})")
                else:
                    print(f"Joystick: X={joy_x:.2f} Y={joy_y:.2f} Z={joy_z:.2f} | RAW: ({qx:.3f}, {qy:.3f}, {qz:.3f}, {qw:.3f})")
            self.last_orientation_debug = now
    
    async def _process_move(self, event: GanCubeMoveEvent):
        """Process move event (async, non-blocking)"""
        move = event.move
        
        # Check for duplicate
        if self.duplicate_filter.is_duplicate(move):
            return
        
        print(f"Move: {move}")
        self.move_count += 1
        
        # Special handling for roll during sprint
        if move == "U'" and self.sprint_machine.sprinting:
            await self.sprint_machine.handle_roll()
            return
        
        # Get action from config
        action = self.config.get('move_mappings', {}).get(move)
        if not action:
            return
        
        # Execute action
        await self._execute_gamepad_action(action)
    
    async def _execute_gamepad_action(self, action: str):
        """Execute gamepad action (async)"""
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
            await asyncio.sleep(0.1)
            self.batcher.release_button(button)
            
        elif action == 'gamepad_r2':
            self.batcher.press_trigger('right', 255)
            await asyncio.sleep(0.1)
            self.batcher.press_trigger('right', 0)
            
        elif action == 'gamepad_l2':
            self.batcher.press_trigger('left', 255)
            await asyncio.sleep(0.1)
            self.batcher.press_trigger('left', 0)
    
    # =========================================================================
    # CALIBRATION & HOTKEYS
    # =========================================================================
    
    async def _auto_calibrate(self):
        """Auto-calibrate after connection"""
        await asyncio.sleep(2.0)
        
        if self.last_raw_quaternion:
            print("\n🔄 Auto-calibrating cube...")
            self.calibrate()
            print("📍 Place cube with GREEN face forward for optimal control\n")
    
    def calibrate(self):
        """Calibrate the cube to current position"""
        if not self.last_raw_quaternion:
            print("ERROR: No cube data yet. Move the cube first.")
            return
        
        self.calibration_reference = self.last_raw_quaternion.copy()
        
        if self.sprint_machine.sprinting:
            self.sprint_machine.stop_sprint()
        
        print(f"CALIBRATION: Reference = ({self.calibration_reference['x']:.3f}, "
              f"{self.calibration_reference['y']:.3f}, {self.calibration_reference['z']:.3f}, "
              f"{self.calibration_reference['w']:.3f})")
        print("Cube calibrated! Current position is now identity (0,0,0,1)")
    
    def _setup_hotkeys(self):
        """Setup keyboard hotkeys"""
        try:
            keyboard.add_hotkey('f5', self._hotkey_recalibrate, suppress=False)
            keyboard.add_hotkey('f6', self._hotkey_toggle_sprint, suppress=False)
            keyboard.add_hotkey('f7', self._hotkey_toggle_debug, suppress=False)
            keyboard.add_hotkey('f9', self._hotkey_reset_joystick, suppress=False)
            
            self.hotkeys_registered = True
            print("\n📌 Hotkeys enabled:")
            print("  F5 - Recalibrate cube")
            print("  F6 - Toggle sprint mode")
            print("  F7 - Toggle debug output")
            print("  F9 - Reset joystick\n")
            
        except Exception as e:
            print(f"Failed to register hotkeys: {e}")
    
    def _hotkey_recalibrate(self):
        if self.last_raw_quaternion:
            print("\n🔄 [F5] Recalibrating cube...")
            self.calibrate()
    
    def _hotkey_toggle_sprint(self):
        self.enable_sprint = not self.enable_sprint
        print(f"\n🏃 [F6] Sprint mode: {'ENABLED' if self.enable_sprint else 'DISABLED'}")
        if not self.enable_sprint and self.sprint_machine.sprinting:
            self.sprint_machine.stop_sprint()
    
    def _hotkey_toggle_debug(self):
        self.show_orientation_debug = not self.show_orientation_debug
        print(f"\n🐛 [F7] Debug output: {'ON' if self.show_orientation_debug else 'OFF'}")
    
    def _hotkey_reset_joystick(self):
        print("\n🎮 [F9] Resetting joystick to center...")
        if self.sprint_machine.sprinting:
            self.sprint_machine.stop_sprint()
        self.batcher.update_orientation(0, 0, 0)
        print("  Joystick centered.")
    
    # =========================================================================
    # MAIN RUN LOOP
    # =========================================================================
    
    async def print_stats_loop(self):
        """Print performance statistics"""
        while True:
            await asyncio.sleep(5)
            
            if self.start_time > 0:
                runtime = time.perf_counter() - self.start_time
                orientation_rate = self.orientation_count / runtime if runtime > 0 else 0
                move_rate = self.move_count / runtime if runtime > 0 else 0
                
                # Check queue sizes
                orient_queue_size = self.orientation_queue.qsize()
                move_queue_size = self.move_queue.qsize()
                
                print(f"\n📊 Stats: {runtime:.0f}s | Orient: {orientation_rate:.1f}Hz | Moves: {move_rate:.2f}Hz | Queues: O={orient_queue_size} M={move_queue_size}")
    
    async def run(self):
        """Main run loop"""
        try:
            # Connect to cube
            await self.connect_cube()
            
            # Start all background tasks
            tasks = [
                asyncio.create_task(self.batcher.flush_loop()),
                asyncio.create_task(self.process_orientation_queue()),
                asyncio.create_task(self.process_move_queue()),
                asyncio.create_task(self.print_stats_loop())
            ]
            
            print("\n✅ V2 Controller (ASYNC) ready!")
            print("Move the cube to control gamepad.")
            print("Press Ctrl+C to exit.\n")
            
            # Run forever
            await asyncio.gather(*tasks)
            
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
    controller = CubeControllerV2Async()
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