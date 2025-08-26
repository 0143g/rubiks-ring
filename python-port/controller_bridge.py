#!/usr/bin/env python3
"""
Gamepad Controller Bridge for GAN Cube
Converts cube moves and orientation to Xbox gamepad input
Windows only - requires vgamepad
"""

import asyncio
import websockets
import json
import time
import sys
import os
from typing import Dict, Set, Any, Optional
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Gamepad imports
try:
    import vgamepad as vg
    GAMEPAD_AVAILABLE = True
except ImportError:
    print("ERROR: vgamepad not available - install: pip install vgamepad")
    print("This controller bridge requires Windows and vgamepad")
    sys.exit(1)

@dataclass
class ControllerConfig:
    """Configuration for controller mappings and sensitivity"""
    mouse_sensitivity: float = 2.0
    movement_sensitivity: float = 2.0
    deadzone: float = 0.1
    rate_limit_ms: int = 1
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
            with open(config_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if not content.strip():
                    print(f"WARNING: Config file {config_path} is empty")
                    return cls(move_mappings={})
                data = json.loads(content)
            
            # Extract settings from JSON structure
            sensitivity = data.get('sensitivity', {})
            deadzone_settings = data.get('deadzone', {})
            timing = data.get('timing', {})
            
            # Get active mapping
            active_mapping = data.get('active_mapping', 'move_mappings')
            if active_mapping in data:
                move_mappings = data[active_mapping]
            else:
                move_mappings = data.get('move_mappings', {})
                
            if not move_mappings:
                print(f"WARNING: No move_mappings found in config file, using empty mappings")
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
            
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid JSON in {config_path}: {e}")
            print(f"Please check the syntax of your config file")
            return cls(move_mappings={})
        except Exception as e:
            print(f"ERROR loading config from {config_path}: {e}")
            # Return instance with empty mappings instead of defaults
            return cls(move_mappings={})
    
    def __post_init__(self):
        if self.move_mappings is None or not self.move_mappings:
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
        
        self.last_input_time = 0
        self.connected_clients: Set = set()
        
        # Sprint/Roll management
        self.sprint_mode_active = False
        self.b_button_held_by_sprint = False
        self.rolling_in_progress = False  # Track if we're currently performing a roll
        
        # Initialize gamepad
        try:
            self.gamepad = vg.VX360Gamepad()
            print("Virtual Xbox controller created")
        except Exception as e:
            print(f"ERROR: Could not create virtual gamepad: {e}")
            sys.exit(1)
        
        # Thread pool for non-blocking gamepad updates
        self.executor = ThreadPoolExecutor(max_workers=1)
                
        print("Gamepad controller bridge initialized")
        print(f"Loaded {len(self.config.move_mappings)} move mappings")
        
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
        
        # Special handling for U' (roll) when in sprint mode
        # Check BEFORE processing AUTO_B commands to avoid conflicts
        if move == "U'" and self.sprint_mode_active:
            await self.handle_roll_during_sprint(move)
            return
        
        # Get mapped action for this move (including AUTO_B_PRESS/RELEASE)
        action = self.config.move_mappings.get(move)
        if not action:
            return
        
        # Update sprint state tracking for AUTO_B commands
        if move == "AUTO_B_PRESS":
            # Only update state and execute action if not already sprinting
            if not self.sprint_mode_active:
                self.sprint_mode_active = True
                print(f"SPRINT: Activating (auto-triggered)")
                await self.execute_action(action, move)
        elif move == "AUTO_B_RELEASE":
            # Only update state and execute action if currently sprinting
            if self.sprint_mode_active:
                self.sprint_mode_active = False
                # Don't release if we're in the middle of a roll
                if not self.rolling_in_progress:
                    print(f"SPRINT: Deactivating (auto-triggered)")
                    await self.execute_action(action, move)
                else:
                    print(f"SPRINT: Skipping release (roll in progress)")
        else:
            # Normal move execution
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
            return
            
        self.rolling_in_progress = True
        was_sprint_held = self.b_button_held_by_sprint
        was_sprint_active = self.sprint_mode_active
        
        try:
            # Step 1: Release B button completely (stop sprint hold)
            if self.b_button_held_by_sprint:
                self.b_button_held_by_sprint = False
                await self._gamepad_button_release(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
            
            # Step 2: Wait for button to fully release
            await asyncio.sleep(0.08)
            
            # Step 3: Do a fresh B press (triggers roll)
            self.gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
            self.gamepad.update()
            
            # Step 4: Hold the press for roll duration
            await asyncio.sleep(0.1)
            
            # Step 5: Release the roll press
            self.gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
            self.gamepad.update()
            
            # Step 6: Wait a moment for roll to finish
            await asyncio.sleep(0.05)
            
            # Step 7: Re-engage sprint hold if still in sprint mode
            # Only re-hold if sprint mode is still active and we were holding before
            if self.sprint_mode_active and was_sprint_active and was_sprint_held:
                self.b_button_held_by_sprint = True
                await self._gamepad_button_hold(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
                
        finally:
            # Always clear the rolling flag
            self.rolling_in_progress = False
    
    async def handle_key_press(self, data: Dict[str, Any]):
        """Deprecated - gamepad only"""
        pass
    
    async def handle_key_release(self, data: Dict[str, Any]):
        """Deprecated - gamepad only"""
        pass
    
    async def handle_mouse_click(self, data: Dict[str, Any]):
        """Deprecated - gamepad only"""
        pass
    
    async def handle_mouse_move(self, data: Dict[str, Any]):
        """Deprecated - gamepad only"""
        pass
    
    async def execute_action(self, action: str, move: str):
        """Execute a mapped gaming action - gamepad only"""
        if action.startswith('gamepad_combo_'):
            await self._execute_gamepad_combo(action, move)
        elif action.startswith('gamepad_'):
            await self._execute_gamepad_action(action, move)
        else:
            print(f"Unsupported action: {action} (gamepad only)")
    
    async def _execute_gamepad_action(self, action: str, move: str):
        """Execute gamepad-specific actions"""
            
        try:
            if action == "gamepad_r1":
                await self._gamepad_button_press(vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER)
            elif action == "gamepad_r2":
                await self._gamepad_trigger_press('right')
            elif action == "gamepad_l2":
                await self._gamepad_trigger_press('left')
            elif action == "gamepad_b":
                await self._gamepad_button_press(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
            elif action == "gamepad_a":
                await self._gamepad_button_press(vg.XUSB_BUTTON.XUSB_GAMEPAD_A)
            elif action == "gamepad_x":
                await self._gamepad_button_press(vg.XUSB_BUTTON.XUSB_GAMEPAD_X)
            elif action == "gamepad_y":
                await self._gamepad_button_press(vg.XUSB_BUTTON.XUSB_GAMEPAD_Y)
            elif action == "gamepad_r3":
                await self._gamepad_button_press(vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB)
            elif action == "gamepad_dpad_right":
                await self._gamepad_button_press(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT)
            elif action == "gamepad_dpad_left":
                await self._gamepad_button_press(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT)
            elif action == "gamepad_dpad_down":
                await self._gamepad_button_press(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN)
            elif action == "gamepad_dpad_up":
                await self._gamepad_button_press(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP)
            elif action == "gamepad_b_hold":
                # Only hold if not already held and not rolling
                if not self.b_button_held_by_sprint and not self.rolling_in_progress:
                    await self._gamepad_button_hold(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
                    self.b_button_held_by_sprint = True
            elif action == "gamepad_b_release":
                # Only release if currently held and not rolling
                if self.b_button_held_by_sprint and not self.rolling_in_progress:
                    await self._gamepad_button_release(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
                    self.b_button_held_by_sprint = False
        except Exception as e:
            pass  # Ignore gamepad errors
    
    async def _execute_gamepad_combo(self, action: str, move: str):
        """Execute gamepad button combos like Y+DpadDown"""
            
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
                return
                
            hold_button_name = buttons[0].strip()
            press_button_name = buttons[1].strip()
            
            hold_button = button_map.get(hold_button_name)
            press_button = button_map.get(press_button_name)
            
            if not hold_button or not press_button:
                return
            
            # Execute the combo: hold first button, press second, release both
            
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
            pass  # Ignore combo errors
    
    async def set_analog_movement(self, tilt_x: float, tilt_y: float, spin_z: float):
        """Set analog stick positions based on cube orientation"""
        # Convert to gamepad range (-32768 to 32767)
        left_stick_x = max(-32768, min(32767, int(tilt_x * 32767 * self.config.movement_sensitivity)))
        left_stick_y = max(-32768, min(32767, int(tilt_y * 32767 * self.config.movement_sensitivity)))
        right_stick_x = max(-32768, min(32767, int(spin_z * 32767 * self.config.movement_sensitivity)))
        
        self.gamepad.left_joystick(x_value=left_stick_x, y_value=left_stick_y)
        self.gamepad.right_joystick(x_value=right_stick_x, y_value=0)
        self.gamepad.update()
    
    # Gamepad helper methods
    async def _gamepad_button_press(self, button):
        """Press and release a gamepad button"""
        self.gamepad.press_button(button=button)
        self.gamepad.update()
        
        # Schedule async release to avoid blocking
        async def release_button():
            await asyncio.sleep(0.1)
            self.gamepad.release_button(button=button)
            self.gamepad.update()
        
        # Schedule the release without waiting for it
        asyncio.create_task(release_button())
    
    async def _gamepad_trigger_press(self, trigger_side: str):
        """Press and release a gamepad trigger"""
        if trigger_side == 'right':
            self.gamepad.right_trigger(value=255)
        elif trigger_side == 'left':
            self.gamepad.left_trigger(value=255)
        
        self.gamepad.update()
        
        # Schedule async release to avoid blocking  
        async def release_trigger():
            await asyncio.sleep(0.1)
            if trigger_side == 'right':
                self.gamepad.right_trigger(value=0)
            elif trigger_side == 'left':
                self.gamepad.left_trigger(value=0)
            self.gamepad.update()
        
        # Schedule the release without waiting for it
        asyncio.create_task(release_trigger())
    
    async def _gamepad_button_hold(self, button):
        """Press and hold a gamepad button (for continuous actions like sprint)"""
        # Track if this button is already being held
        button_attr = f'_auto_button_{button}_held'
        if getattr(self, button_attr, False):
            return  # Already holding this button
        
        self.gamepad.press_button(button=button)
        self.gamepad.update()
        setattr(self, button_attr, True)
    
    async def _gamepad_button_release(self, button):
        """Release a held gamepad button"""
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
        # Reset sprint state
        self.sprint_mode_active = False
        self.b_button_held_by_sprint = False
        self.rolling_in_progress = False
        
        # Release any auto-held buttons
        for attr_name in dir(self):
            if attr_name.startswith('_auto_button_') and attr_name.endswith('_held'):
                if getattr(self, attr_name, False):
                    setattr(self, attr_name, False)
        
        self.gamepad.reset()
        self.gamepad.update()

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
        print(f"Client connected: {client_addr}")
        
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
            pass
        except Exception as e:
            pass
        finally:
            self.controller.connected_clients.discard(websocket)
            if not self.controller.connected_clients:
                await self.controller.release_all_inputs()
    
    async def start_server(self):
        """Start the WebSocket server"""
        print("Gamepad Controller Bridge")
        print(f"Starting server on {self.host}:{self.port}")
        
        try:
            async with websockets.serve(self.handle_client, self.host, self.port):
                print(f"Server ready")
                await asyncio.Future()  # Run forever
        except KeyboardInterrupt:
            print("Server stopped")
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
        print("Shutting down")
    except Exception as e:
        print(f"Error: {e}")
