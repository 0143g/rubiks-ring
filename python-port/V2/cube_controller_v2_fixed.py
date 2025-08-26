#!/usr/bin/env python3
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
from gan_web_bluetooth.utils import now

# Gamepad import
try:
    import vgamepad as vg
    GAMEPAD_AVAILABLE = True
except ImportError:
    print("ERROR: vgamepad not available - install: pip install vgamepad")
    print("This controller requires Windows and vgamepad")
    sys.exit(1)

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
        
    def update_orientation(self, pitch: float):
        """Update sprint state based on forward tilt"""
        should_sprint = pitch > self.forward_tilt_threshold
        
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
        self.enable_sprint = False  # Can be toggled
        self.last_orientation_time = 0
        
        # Performance monitoring
        self.orientation_count = 0
        self.move_count = 0
        self.start_time = 0
        
        print("V2 Cube Controller (Fixed) initialized")
        print(f"Loaded {len(self.config.get('move_mappings', {}))} move mappings")
        
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
                    print(f"Loaded config from: {path}")
                    return config
                    
        print("WARNING: No config file found, using defaults")
        return {"move_mappings": {}}
        
    async def connect_cube(self):
        """Connect to cube using gan_web_bluetooth"""
        print("Connecting to GAN cube...")
        
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
        # Rate limiting check
        now = time.perf_counter_ns() // 1_000_000
        if now - self.last_orientation_time < 8:  # 125Hz max
            return
        self.last_orientation_time = now
        
        self.orientation_count += 1
        
        # Extract quaternion
        qx = event.quaternion.x
        qy = event.quaternion.y
        qz = event.quaternion.z
        qw = event.quaternion.w
        
        # Convert quaternion to Euler angles
        # Roll (x-axis rotation)
        sinr_cosp = 2 * (qw * qx + qy * qz)
        cosr_cosp = 1 - 2 * (qx * qx + qy * qy)
        roll = math.atan2(sinr_cosp, cosr_cosp)
        
        # Pitch (y-axis rotation)
        sinp = 2 * (qw * qy - qz * qx)
        if abs(sinp) >= 1:
            pitch = math.copysign(math.pi / 2, sinp)
        else:
            pitch = math.asin(sinp)
            
        # Yaw (z-axis rotation)
        siny_cosp = 2 * (qw * qz + qx * qy)
        cosy_cosp = 1 - 2 * (qy * qy + qz * qz)
        yaw = math.atan2(siny_cosp, cosy_cosp)
        
        # Convert to normalized range
        roll_norm = roll / math.pi
        pitch_norm = pitch / (math.pi / 2)
        yaw_norm = yaw / math.pi
        
        # Apply sensitivity
        sensitivity = self.config.get('sensitivity', {})
        movement_sens = sensitivity.get('movement_sensitivity', 2.0)
        spin_sens = sensitivity.get('spin_z_sensitivity', 1.5)
        
        # Map to joystick
        joy_x = pitch_norm * movement_sens
        joy_y = roll_norm * movement_sens
        joy_z = yaw_norm * spin_sens
        
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
        
        # Update sprint state if enabled
        if self.enable_sprint:
            self.sprint_machine.update_orientation(pitch_norm)
        
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
            
    async def print_stats_loop(self):
        """Print performance statistics"""
        while True:
            await asyncio.sleep(5)
            
            if self.start_time > 0:
                runtime = time.perf_counter() - self.start_time
                orientation_rate = self.orientation_count / runtime if runtime > 0 else 0
                move_rate = self.move_count / runtime if runtime > 0 else 0
                
                print(f"\n📊 Stats: {runtime:.0f}s | Orientation: {orientation_rate:.1f}Hz | Moves: {move_rate:.2f}Hz")
                
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