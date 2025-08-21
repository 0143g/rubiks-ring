#!/usr/bin/env python3
"""
Cross-Platform Gaming Controller Bridge for GAN Cube
Converts cube moves and orientation to gaming input (keyboard, mouse, gamepad)
Supports Windows, Linux, macOS with platform-specific optimizations
"""

import asyncio
import websockets
import json
import time
import sys
import platform
import os
from typing import Dict, Set, Any, Optional
from dataclasses import dataclass
from pathlib import Path

# Platform-specific imports
PLATFORM = platform.system()

if PLATFORM == "Windows":
    try:
        import win32api
        import win32con
        WINDOWS_AVAILABLE = True
    except ImportError:
        print("Windows libraries not available - install: pip install pywin32")
        WINDOWS_AVAILABLE = False
    
    try:
        import vgamepad as vg
        GAMEPAD_AVAILABLE = True
    except ImportError:
        print("Virtual gamepad not available - install: pip install vgamepad")
        GAMEPAD_AVAILABLE = False

elif PLATFORM == "Linux":
    try:
        import pyautogui
        import subprocess
        LINUX_AVAILABLE = True
    except ImportError:
        print("Linux input libraries not available - install: pip install pyautogui")
        LINUX_AVAILABLE = False
    GAMEPAD_AVAILABLE = False  # TODO: Add Linux gamepad support

elif PLATFORM == "Darwin":  # macOS
    try:
        import pyautogui
        MACOS_AVAILABLE = True
    except ImportError:
        print("macOS input libraries not available - install: pip install pyautogui")
        MACOS_AVAILABLE = False
    GAMEPAD_AVAILABLE = False  # TODO: Add macOS gamepad support

else:
    print(f"Unsupported platform: {PLATFORM}")
    sys.exit(1)

@dataclass
class ControllerConfig:
    """Configuration for controller mappings and sensitivity"""
    mouse_sensitivity: float = 2.0
    movement_sensitivity: float = 2.0
    deadzone: float = 0.1
    rate_limit_ms: int = 16  # 60 FPS
    forward_tilt_threshold: float = 0.7
    
    # Dashboard sensitivity settings
    tilt_x_sensitivity: float = 2.5
    tilt_y_sensitivity: float = 2.5
    spin_z_sensitivity: float = 2.0
    spin_deadzone: float = 0.02
    
    # Move mappings
    move_mappings: Dict[str, str] = None
    active_mapping: str = "move_mappings"
    
    @classmethod
    def load_from_json(cls, config_path: str = "controller_config.json"):
        """Load configuration from JSON file"""
        config_file = Path(config_path)
        if not config_file.exists():
            print(f"ERROR: Config file {config_path} not found!")
            print(f"Please create a {config_path} file with your move_mappings")
            # Return instance with empty mappings instead of defaults
            return cls(move_mappings={})
            
        try:
            with open(config_file, 'r') as f:
                data = json.load(f)
            
            # Extract settings from JSON structure
            sensitivity = data.get('sensitivity', {})
            deadzone_settings = data.get('deadzone', {})
            timing = data.get('timing', {})
            
            # Get active mapping
            active_mapping = data.get('active_mapping', 'move_mappings')
            if active_mapping in data:
                move_mappings = data[active_mapping]
            else:
                move_mappings = data.get('move_mappings', None)
                
            if move_mappings is None:
                print(f"ERROR: No '{active_mapping}' found in config file!")
                move_mappings = {}
            
            return cls(
                mouse_sensitivity=sensitivity.get('mouse_sensitivity', 2.0),
                movement_sensitivity=sensitivity.get('movement_sensitivity', 2.0),
                deadzone=deadzone_settings.get('bridge_deadzone', 0.1),
                rate_limit_ms=timing.get('rate_limit_ms', 16),
                forward_tilt_threshold=timing.get('forward_tilt_threshold', 0.7),
                tilt_x_sensitivity=sensitivity.get('tilt_x_sensitivity', 2.5),
                tilt_y_sensitivity=sensitivity.get('tilt_y_sensitivity', 2.5),
                spin_z_sensitivity=sensitivity.get('spin_z_sensitivity', 2.0),
                spin_deadzone=deadzone_settings.get('spin_deadzone', 0.1),
                move_mappings=move_mappings,
                active_mapping=active_mapping
            )
            
        except Exception as e:
            print(f"ERROR loading config from {config_path}: {e}")
            # Return instance with empty mappings instead of defaults
            return cls(move_mappings={})
    
    def __post_init__(self):
        if self.move_mappings is None:
            print("ERROR: No move_mappings found in config file!")
            print(f"Please ensure {self.active_mapping} exists in your controller_config.json")
            self.move_mappings = {}  # Empty dict instead of defaults

class CrossPlatformController:
    """Cross-platform gaming input controller"""
    
    def __init__(self, config: ControllerConfig = None, config_path: str = "controller_config.json"):
        self.config_path = config_path
        self.config = config or ControllerConfig.load_from_json(config_path)
        self.config_mtime = self._get_config_mtime()
        
        self.active_keys: Set[str] = set()
        self.last_input_time = 0
        self.connected_clients: Set = set()
        
        # Sprint/Roll management
        self.sprint_mode_active = False
        self.b_button_held_by_sprint = False
        self.rolling_in_progress = False  # Track if we're currently performing a roll
        
        # Platform-specific initialization
        self.gamepad = None
        if PLATFORM == "Windows" and WINDOWS_AVAILABLE and GAMEPAD_AVAILABLE:
            try:
                self.gamepad = vg.VX360Gamepad()
                print("Virtual Xbox controller created (Windows)")
            except Exception as e:
                print(f"Could not create virtual gamepad: {e}")
                
        print(f"Controller bridge initialized for {PLATFORM}")
        print(f"Loaded config: {self.config.active_mapping} mapping with {len(self.config.move_mappings)} moves")
        print(f"Sensitivities - Mouse: {self.config.mouse_sensitivity}, Movement: {self.config.movement_sensitivity}")
        print(f"Deadzones - General: {self.config.deadzone}, Spin: {self.config.spin_deadzone}")
        
    async def handle_message(self, data: Dict[str, Any]):
        """Process incoming WebSocket message from cube dashboard"""
        # Check for config file changes before processing messages
        self._check_and_reload_config()
        
        msg_type = data.get('type', '')
        
        if msg_type == 'CUBE_MOVE':
            await self.handle_cube_move(data)
        elif msg_type == 'CUBE_ORIENTATION':
            await self.handle_orientation(data)
        elif msg_type == 'KEY_PRESS':
            await self.handle_key_press(data)
        elif msg_type == 'KEY_RELEASE':
            await self.handle_key_release(data)
        elif msg_type == 'MOUSE_CLICK':
            await self.handle_mouse_click(data)
        elif msg_type == 'MOUSE_MOVE':
            await self.handle_mouse_move(data)
    
    async def handle_cube_move(self, data: Dict[str, Any]):
        """Handle cube face moves and convert to game input"""
        move = data.get('move', '')
        print(f"Cube move: {move}")
        
        # Handle auto sprint commands and update our sprint state
        if move == "AUTO_B_PRESS":
            self.sprint_mode_active = True
            # DON'T set b_button_held_by_sprint = True here, let the normal action handle B press
            print(f"🏃 SPRINT MODE: ON (dashboard triggered)")
        elif move == "AUTO_B_RELEASE":
            self.sprint_mode_active = False  
            # DON'T set b_button_held_by_sprint = False here, let the normal action handle B release
            print(f"🚶 SPRINT MODE: OFF (dashboard triggered)")
        
        # DEBUG: Check sprint state (reduced frequency)
        if move in ['U\'', 'AUTO_B_PRESS', 'AUTO_B_RELEASE']:  # Only debug important moves
            print(f"DEBUG: move='{move}', sprint_mode_active={self.sprint_mode_active}, b_button_held_by_sprint={self.b_button_held_by_sprint}")
        
        # Special handling for U' (roll) when in sprint mode
        if move == "U'" and self.sprint_mode_active:
            print(f"🔥 TRIGGERING SMART ROLL for {move}")
            await self.handle_roll_during_sprint(move)
            return
        
        # Get mapped action for this move
        action = self.config.move_mappings.get(move)
        if not action:
            print(f"No mapping for move: {move}")
            return
            
        await self.execute_action(action, move)
    
    async def handle_orientation(self, data: Dict[str, Any]):
        """Handle cube orientation for analog movement"""
        if not self._should_process_input():
            return
            
        tilt_x = data.get('tiltX', 0.0)  # Left/Right tilt
        tilt_y = data.get('tiltY', 0.0)  # Forward/Back tilt  
        spin_z = data.get('spinZ', 0.0)  # Rotation around vertical axis
        
        # Apply deadzone
        if abs(tilt_x) < self.config.deadzone:
            tilt_x = 0.0
        if abs(tilt_y) < self.config.deadzone:
            tilt_y = 0.0
        if abs(spin_z) < self.config.spin_deadzone:
            spin_z = 0.0
        
        # Sprint mode management disabled - dashboard handles this via AUTO_B_PRESS/RELEASE
        # await self.manage_sprint_mode(tilt_y)
            
        await self.set_analog_movement(tilt_x, tilt_y, spin_z)
    
    async def manage_sprint_mode(self, tilt_y: float):
        """Manage auto-sprint mode based on forward tilt"""
        if not self.gamepad or not GAMEPAD_AVAILABLE:
            return  # Sprint mode only works with gamepad
            
        # Don't change sprint state while rolling
        if self.rolling_in_progress:
            return
            
        forward_tilt = tilt_y
        
        # Check if we should enter sprint mode
        if forward_tilt >= self.config.forward_tilt_threshold and not self.sprint_mode_active:
            self.sprint_mode_active = True
            if not self.b_button_held_by_sprint:  # Only hold if not already held
                self.b_button_held_by_sprint = True
                await self._gamepad_button_hold(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
                print(f"SPRINT MODE: ON (forward tilt: {forward_tilt:.2f})")
        
        # Check if we should exit sprint mode
        elif forward_tilt < (self.config.forward_tilt_threshold - 0.1) and self.sprint_mode_active:  # Hysteresis
            self.sprint_mode_active = False
            if self.b_button_held_by_sprint:
                self.b_button_held_by_sprint = False
                await self._gamepad_button_release(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
                print(f"SPRINT MODE: OFF (forward tilt: {forward_tilt:.2f})")
    
    async def handle_roll_during_sprint(self, move: str):
        """Handle U' (roll) move when sprinting - release B, do B press (roll), then re-hold B"""
        if not self.gamepad or not GAMEPAD_AVAILABLE:
            return  # Smart roll only works with gamepad
        
        # Prevent concurrent rolls
        if self.rolling_in_progress:
            print(f"SMART ROLL: {move} ignored - roll already in progress")
            return
            
        self.rolling_in_progress = True
        was_sprint_held = self.b_button_held_by_sprint
        
        try:
            print(f"SMART ROLL: {move} while sprinting - executing release→press→hold sequence")
            
            # Step 1: Release B button completely (stop sprint hold)
            if self.b_button_held_by_sprint:
                self.b_button_held_by_sprint = False
                await self._gamepad_button_release(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
                print("  Released B hold (stopped sprint)")
            
            # Step 2: Wait for button to fully release
            await asyncio.sleep(0.08)  # Slightly longer to ensure clean release
            
            # Step 3: Now do a fresh B press (this triggers the roll in-game)
            # This is a full press-release cycle while still moving forward
            self.gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
            self.gamepad.update()
            print(f"  B PRESSED (roll triggered) - still moving forward")
            
            # Step 4: Hold the press for roll duration
            await asyncio.sleep(0.1)  # Hold for roll execution
            
            # Step 5: Release the roll press
            self.gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
            self.gamepad.update()
            print(f"  B RELEASED (roll complete)")
            
            # Step 6: Wait a moment for roll to finish
            await asyncio.sleep(0.05)
            
            # Step 7: Re-engage sprint hold if still in sprint mode
            if self.sprint_mode_active and was_sprint_held:
                self.b_button_held_by_sprint = True
                await self._gamepad_button_hold(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
                print("  Re-engaged B hold (sprint restored)")
                
        finally:
            # Always clear the rolling flag
            self.rolling_in_progress = False
            print(f"SMART ROLL: {move} sequence complete")
    
    async def handle_key_press(self, data: Dict[str, Any]):
        """Handle continuous key press"""
        key = data.get('key', '').lower()
        if key not in self.active_keys:
            await self.key_down(key)
            self.active_keys.add(key)
            print(f"Key DOWN: {key.upper()}")
    
    async def handle_key_release(self, data: Dict[str, Any]):
        """Handle key release"""
        key = data.get('key', '').lower()
        if key in self.active_keys:
            await self.key_up(key)
            self.active_keys.remove(key)
            print(f"Key UP: {key.upper()}")
    
    async def handle_mouse_click(self, data: Dict[str, Any]):
        """Handle mouse clicks"""
        button = data.get('button', 'left')
        await self.mouse_click(button)
        print(f"Mouse {button.upper()} click")
    
    async def handle_mouse_move(self, data: Dict[str, Any]):
        """Handle mouse movement with rate limiting"""
        if not self._should_process_input():
            return
            
        delta_x = int(data.get('deltaX', 0) * self.config.mouse_sensitivity)
        delta_y = int(data.get('deltaY', 0) * self.config.mouse_sensitivity)
        
        if delta_x != 0 or delta_y != 0:
            await self.mouse_move_relative(delta_x, delta_y)
            print(f"Mouse → ({delta_x:+d}, {delta_y:+d})")
    
    async def execute_action(self, action: str, move: str):
        """Execute a mapped gaming action"""
        if action.startswith('gamepad_combo_') and self.gamepad:
            await self._execute_gamepad_combo(action, move)
        elif action.startswith('gamepad_') and self.gamepad:
            await self._execute_gamepad_action(action, move)
        elif action.startswith('key_'):
            key = action[4:]  # Remove 'key_' prefix
            await self.key_press(key)
        elif action.startswith('mouse_'):
            button = action[6:]  # Remove 'mouse_' prefix
            await self.mouse_click(button)
        else:
            print(f"Unknown action: {action}")
    
    async def _execute_gamepad_action(self, action: str, move: str):
        """Execute gamepad-specific actions"""
        if not self.gamepad:
            return
            
        try:
            if action == "gamepad_r1":
                await self._gamepad_button_press(vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER)
                print(f"  Gamepad R1 (Right Bumper) → {move}")
            elif action == "gamepad_r2":
                await self._gamepad_trigger_press('right')
                print(f"  Gamepad R2 (Right Trigger) → {move}")
            elif action == "gamepad_l2":
                await self._gamepad_trigger_press('left')
                print(f"  Gamepad L2 (Left Trigger) → {move}")
            elif action == "gamepad_b":
                await self._gamepad_button_press(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
                print(f"  Gamepad B Button → {move}")
            elif action == "gamepad_a":
                await self._gamepad_button_press(vg.XUSB_BUTTON.XUSB_GAMEPAD_A)
                print(f"  Gamepad A Button → {move}")
            elif action == "gamepad_x":
                await self._gamepad_button_press(vg.XUSB_BUTTON.XUSB_GAMEPAD_X)
                print(f"  Gamepad X Button → {move}")
            elif action == "gamepad_y":
                await self._gamepad_button_press(vg.XUSB_BUTTON.XUSB_GAMEPAD_Y)
                print(f"  Gamepad Y Button → {move}")
            elif action == "gamepad_r3":
                await self._gamepad_button_press(vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB)
                print(f"  Gamepad R3 (Right Stick Press) → {move}")
            elif action == "gamepad_dpad_right":
                await self._gamepad_button_press(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT)
                print(f"  Gamepad D-Pad Right → {move}")
            elif action == "gamepad_dpad_left":
                await self._gamepad_button_press(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT)
                print(f"  Gamepad D-Pad Left → {move}")
            elif action == "gamepad_b_hold":
                await self._gamepad_button_hold(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
                self.b_button_held_by_sprint = True  # Track that we're holding B for sprint
                print(f"  AUTO B BUTTON: PRESSED (sprint mode)")
            elif action == "gamepad_b_release":
                await self._gamepad_button_release(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
                self.b_button_held_by_sprint = False  # Track that we released B
                print(f"  AUTO B BUTTON: RELEASED (normal mode)")
        except Exception as e:
            print(f"Gamepad action failed: {e}")
    
    async def _execute_gamepad_combo(self, action: str, move: str):
        """Execute gamepad button combos like Y+DpadDown"""
        if not self.gamepad:
            return
            
        # Parse combo format: gamepad_combo_y+dpad_down
        combo_part = action.replace('gamepad_combo_', '')
        
        # Map button names to vgamepad constants
        button_map = {
            'a': vg.XUSB_BUTTON.XUSB_GAMEPAD_A,
            'b': vg.XUSB_BUTTON.XUSB_GAMEPAD_B,
            'x': vg.XUSB_BUTTON.XUSB_GAMEPAD_X,
            'y': vg.XUSB_BUTTON.XUSB_GAMEPAD_Y,
            'l1': vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER,
            'r1': vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER,
            'l3': vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_THUMB,
            'r3': vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB,
            'dpad_up': vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP,
            'dpad_down': vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN,
            'dpad_left': vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT,
            'dpad_right': vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT,
            'back': vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK,
            'start': vg.XUSB_BUTTON.XUSB_GAMEPAD_START,
        }
        
        try:
            # Split by + to get the buttons
            buttons = combo_part.split('+')
            if len(buttons) != 2:
                print(f"Invalid combo format: {action}. Use format: gamepad_combo_button1+button2")
                return
                
            hold_button_name = buttons[0].strip()
            press_button_name = buttons[1].strip()
            
            hold_button = button_map.get(hold_button_name)
            press_button = button_map.get(press_button_name)
            
            if not hold_button or not press_button:
                print(f"Unknown button in combo: {action}")
                return
            
            # Execute the combo: hold first button, press second, release both
            print(f"  Gamepad Combo: {hold_button_name.upper()} + {press_button_name.upper()} → {move}")
            
            # Step 1: Press and hold the first button
            self.gamepad.press_button(button=hold_button)
            self.gamepad.update()
            
            # Step 2: Small delay to ensure the hold registers
            await asyncio.sleep(0.05)
            
            # Step 3: Press the second button while still holding first
            self.gamepad.press_button(button=press_button)
            self.gamepad.update()
            
            # Step 4: Hold both buttons briefly
            await asyncio.sleep(0.1)
            
            # Step 5: Release second button first
            self.gamepad.release_button(button=press_button)
            self.gamepad.update()
            
            # Step 6: Small delay
            await asyncio.sleep(0.05)
            
            # Step 7: Release first button
            self.gamepad.release_button(button=hold_button)
            self.gamepad.update()
            
        except Exception as e:
            print(f"Gamepad combo failed: {e}")
    
    async def set_analog_movement(self, tilt_x: float, tilt_y: float, spin_z: float):
        """Set analog stick positions based on cube orientation"""
        if self.gamepad:
            # Convert to gamepad range (-32768 to 32767)
            # tilt_x controls left/right, tilt_y controls forward/back
            left_stick_x = max(-32768, min(32767, int(tilt_x * 32767 * self.config.movement_sensitivity)))
            left_stick_y = max(-32768, min(32767, int(tilt_y * 32767 * self.config.movement_sensitivity)))
            right_stick_x = max(-32768, min(32767, int(spin_z * 32767 * self.config.movement_sensitivity)))
            
            self.gamepad.left_joystick(x_value=left_stick_x, y_value=left_stick_y)
            self.gamepad.right_joystick(x_value=right_stick_x, y_value=0)
            self.gamepad.update()
            
            # Reduce analog stick debug spam - only print significant movements
            if abs(left_stick_x) > 5000 or abs(left_stick_y) > 5000 or abs(right_stick_x) > 5000:
                print(f"Left: ({left_stick_x}, {left_stick_y}) | Right: ({right_stick_x}, 0)")
        else:
            # Fallback to WASD keys for movement
            await self._set_wasd_movement(tilt_x, tilt_y)
            await self._set_mouse_camera(spin_z)
    
    async def _set_wasd_movement(self, tilt_x: float, tilt_y: float):
        """Convert tilt to WASD key presses"""
        threshold = 0.3
        
        # Release old keys
        for key in ['w', 'a', 's', 'd']:
            if key in self.active_keys:
                await self.key_up(key)
                self.active_keys.remove(key)
        
        # Press new keys based on tilt
        if tilt_y < -threshold:  # Forward tilt
            await self.key_down('w')
            self.active_keys.add('w')
        elif tilt_y > threshold:  # Backward tilt
            await self.key_down('s')
            self.active_keys.add('s')
            
        if tilt_x < -threshold:  # Left tilt
            await self.key_down('a')
            self.active_keys.add('a')
        elif tilt_x > threshold:  # Right tilt
            await self.key_down('d')
            self.active_keys.add('d')
    
    async def _set_mouse_camera(self, spin_z: float):
        """Convert spin to mouse camera movement"""
        if abs(spin_z) > 0.1:
            delta_x = int(spin_z * 10 * self.config.mouse_sensitivity)
            await self.mouse_move_relative(delta_x, 0)
    
    # Platform-specific input implementations
    async def key_press(self, key: str):
        """Send single key press"""
        await self.key_down(key)
        await asyncio.sleep(0.05)
        await self.key_up(key)
    
    async def key_down(self, key: str):
        """Send key down event"""
        if PLATFORM == "Windows" and WINDOWS_AVAILABLE:
            await self._windows_key_down(key)
        else:
            await self._generic_key_down(key)
    
    async def key_up(self, key: str):
        """Send key up event"""
        if PLATFORM == "Windows" and WINDOWS_AVAILABLE:
            await self._windows_key_up(key)
        else:
            await self._generic_key_up(key)
    
    async def mouse_click(self, button: str):
        """Send mouse click"""
        if PLATFORM == "Windows" and WINDOWS_AVAILABLE:
            await self._windows_mouse_click(button)
        else:
            await self._generic_mouse_click(button)
    
    async def mouse_move_relative(self, dx: int, dy: int):
        """Move mouse cursor relatively"""
        if PLATFORM == "Windows" and WINDOWS_AVAILABLE:
            await self._windows_mouse_move(dx, dy)
        else:
            await self._generic_mouse_move(dx, dy)
    
    # Windows-specific implementations
    async def _windows_key_down(self, key: str):
        """Windows key down implementation"""
        vk_code = self._get_windows_vk_code(key)
        if vk_code:
            win32api.keybd_event(vk_code, 0, 0, 0)
    
    async def _windows_key_up(self, key: str):
        """Windows key up implementation"""
        vk_code = self._get_windows_vk_code(key)
        if vk_code:
            win32api.keybd_event(vk_code, 0, win32con.KEYEVENTF_KEYUP, 0)
    
    async def _windows_mouse_click(self, button: str):
        """Windows mouse click implementation"""
        if button == "left":
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0)
        elif button == "right":
            win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0)
            win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0)
    
    async def _windows_mouse_move(self, dx: int, dy: int):
        """Windows mouse move implementation"""
        win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, dx, dy)
    
    def _get_windows_vk_code(self, key: str) -> Optional[int]:
        """Get Windows virtual key code"""
        key_map = {
            'a': 0x41, 'b': 0x42, 'c': 0x43, 'd': 0x44, 'e': 0x45, 'f': 0x46,
            'g': 0x47, 'h': 0x48, 'i': 0x49, 'j': 0x4A, 'k': 0x4B, 'l': 0x4C,
            'm': 0x4D, 'n': 0x4E, 'o': 0x4F, 'p': 0x50, 'q': 0x51, 'r': 0x52,
            's': 0x53, 't': 0x54, 'u': 0x55, 'v': 0x56, 'w': 0x57, 'x': 0x58,
            'y': 0x59, 'z': 0x5A,
            'space': win32con.VK_SPACE,
            'shift': win32con.VK_SHIFT,
            'ctrl': win32con.VK_CONTROL,
            'alt': win32con.VK_MENU,
            'tab': win32con.VK_TAB,
            'enter': win32con.VK_RETURN,
            'escape': win32con.VK_ESCAPE
        }
        return key_map.get(key.lower())
    
    # Generic implementations (Linux/macOS)
    async def _generic_key_down(self, key: str):
        """Generic key down using pyautogui"""
        try:
            pyautogui.keyDown(key)
        except Exception as e:
            print(f"Key down failed: {e}")
    
    async def _generic_key_up(self, key: str):
        """Generic key up using pyautogui"""
        try:
            pyautogui.keyUp(key)
        except Exception as e:
            print(f"Key up failed: {e}")
    
    async def _generic_mouse_click(self, button: str):
        """Generic mouse click using pyautogui"""
        try:
            pyautogui.click(button=button)
        except Exception as e:
            print(f"Mouse click failed: {e}")
    
    async def _generic_mouse_move(self, dx: int, dy: int):
        """Generic mouse move using pyautogui"""
        try:
            pyautogui.moveRel(dx, dy)
        except Exception as e:
            print(f"Mouse move failed: {e}")
    
    # Gamepad helper methods
    async def _gamepad_button_press(self, button):
        """Press and release a gamepad button"""
        if not self.gamepad:
            return
        
        self.gamepad.press_button(button=button)
        self.gamepad.update()
        
        # Schedule async release to avoid blocking
        async def release_button():
            await asyncio.sleep(0.1)
            if self.gamepad:  # Check if gamepad still exists
                self.gamepad.release_button(button=button)
                self.gamepad.update()
        
        # Schedule the release without waiting for it
        asyncio.create_task(release_button())
    
    async def _gamepad_trigger_press(self, trigger_side: str):
        """Press and release a gamepad trigger"""
        if not self.gamepad:
            return
        
        if trigger_side == 'right':
            self.gamepad.right_trigger(value=255)
        elif trigger_side == 'left':
            self.gamepad.left_trigger(value=255)
        
        self.gamepad.update()
        
        # Schedule async release to avoid blocking  
        async def release_trigger():
            await asyncio.sleep(0.1)
            if self.gamepad:  # Check if gamepad still exists
                if trigger_side == 'right':
                    self.gamepad.right_trigger(value=0)
                elif trigger_side == 'left':
                    self.gamepad.left_trigger(value=0)
                self.gamepad.update()
        
        # Schedule the release without waiting for it
        asyncio.create_task(release_trigger())
    
    async def _gamepad_button_hold(self, button):
        """Press and hold a gamepad button (for continuous actions like sprint)"""
        if not self.gamepad:
            return
        
        # Track if this button is already being held
        button_attr = f'_auto_button_{button}_held'
        if getattr(self, button_attr, False):
            return  # Already holding this button
        
        self.gamepad.press_button(button=button)
        self.gamepad.update()
        setattr(self, button_attr, True)
    
    async def _gamepad_button_release(self, button):
        """Release a held gamepad button"""
        if not self.gamepad:
            return
        
        # Track if this button is currently being held
        button_attr = f'_auto_button_{button}_held'
        if not getattr(self, button_attr, False):
            return  # Button not currently held
        
        self.gamepad.release_button(button=button)
        self.gamepad.update()
        setattr(self, button_attr, False)
    
    def _get_config_mtime(self) -> float:
        """Get modification time of config file"""
        try:
            return os.path.getmtime(self.config_path)
        except (OSError, FileNotFoundError):
            return 0.0
    
    def _check_and_reload_config(self):
        """Check if config file has been modified and reload if necessary"""
        try:
            current_mtime = self._get_config_mtime()
            if current_mtime > self.config_mtime:
                print("\n🔄 Config file changed, reloading...")
                old_mapping = self.config.active_mapping
                self.config = ControllerConfig.load_from_json(self.config_path)
                self.config_mtime = current_mtime
                
                if old_mapping != self.config.active_mapping:
                    print(f"Mapping changed: {old_mapping} → {self.config.active_mapping}")
                
                print(f"✅ Config reloaded: {len(self.config.move_mappings)} moves")
                print(f"Sensitivities - Mouse: {self.config.mouse_sensitivity}, Movement: {self.config.movement_sensitivity}")
                print(f"Deadzones - General: {self.config.deadzone}, Spin: {self.config.spin_deadzone}")
        except Exception as e:
            print(f"Error reloading config: {e}")
    
    def _should_process_input(self) -> bool:
        """Check if we should process input based on rate limiting"""
        current_time = time.time() * 1000  # Convert to milliseconds
        if current_time - self.last_input_time < self.config.rate_limit_ms:
            return False
        self.last_input_time = current_time
        return True
    
    async def release_all_inputs(self):
        """Release all currently active inputs and reset gamepad"""
        for key in list(self.active_keys):
            await self.key_up(key)
        self.active_keys.clear()
        
        # Reset sprint state
        self.sprint_mode_active = False
        self.b_button_held_by_sprint = False
        self.rolling_in_progress = False
        
        if self.gamepad:
            # Release any auto-held buttons
            for attr_name in dir(self):
                if attr_name.startswith('_auto_button_') and attr_name.endswith('_held'):
                    if getattr(self, attr_name, False):
                        setattr(self, attr_name, False)
                        print("Auto button released")
            
            self.gamepad.reset()
            self.gamepad.update()
            print("All inputs and gamepad reset (including sprint mode)")
        else:
            print("All inputs released")

class ControllerBridgeServer:
    """WebSocket server that bridges cube events to gaming input"""
    
    def __init__(self, port: int = 8083, host: str = "localhost"):
        self.port = port
        self.host = host
        self.controller = CrossPlatformController()
    
    async def handle_client(self, websocket):
        """Handle incoming WebSocket connections"""
        client_addr = websocket.remote_address
        self.controller.connected_clients.add(websocket)
        print(f"Client connected from {client_addr}")
        print("Ready to receive cube commands!")
        
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self.controller.handle_message(data)
                except json.JSONDecodeError as e:
                    print(f"Invalid JSON: {e}")
                except Exception as e:
                    print(f"Error processing message: {e}")
        
        except websockets.exceptions.ConnectionClosed:
            print(f"Client disconnected: {client_addr}")
        except Exception as e:
            print(f"Connection error: {e}")
        finally:
            self.controller.connected_clients.discard(websocket)
            if not self.controller.connected_clients:
                await self.controller.release_all_inputs()
    
    async def start_server(self):
        """Start the WebSocket server"""
        print(f"GAN Cube → Gaming Controller Bridge ({PLATFORM})")
        print(f"Starting WebSocket server on {self.host}:{self.port}")
        print("Waiting for cube dashboard to connect...")
        print()
        
        try:
            async with websockets.serve(self.handle_client, self.host, self.port):
                print(f"Server started successfully on {self.host}:{self.port}")
                await asyncio.Future()  # Run forever
        except KeyboardInterrupt:
            print("\nServer stopped by user")
        finally:
            await self.controller.release_all_inputs()

async def main():
    """Main entry point"""
    server = ControllerBridgeServer()
    await server.start_server()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Server error: {e}")
        input("Press Enter to exit...")
