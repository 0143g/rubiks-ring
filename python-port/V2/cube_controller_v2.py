#!/usr/bin/env python3
"""
V2 Cube Controller - Direct BLE to Gamepad
Single file, minimal latency implementation
Target: 100-110ms total latency (cube hardware + processing)
"""

import asyncio
import time
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from collections import deque

# BLE and encryption imports
from bleak import BleakClient, BleakScanner
from Crypto.Cipher import AES
from Crypto.Util import Counter

# Gamepad import
try:
    import vgamepad as vg
    GAMEPAD_AVAILABLE = True
except ImportError:
    print("ERROR: vgamepad not available - install: pip install vgamepad")
    print("This controller requires Windows and vgamepad")
    sys.exit(1)


# ============================================================================
# CONSTANTS
# ============================================================================

# GAN Cube BLE Services and Characteristics
GAN_GEN2_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dc4179"
GAN_GEN2_STATE_CHAR = "6e400003-b5a3-f393-e0a9-e50e24dc4179"
GAN_GEN2_COMMAND_CHAR = "6e400002-b5a3-f393-e0a9-e50e24dc4179"

# GAN Encryption Keys (from gan_web_bluetooth/definitions.py)
GAN_ENCRYPTION_KEY = bytes([198, 202, 21, 223, 79, 110, 19, 182, 119, 130, 165, 21, 229, 214, 111, 218])
GAN_ENCRYPTION_IV = bytes([135, 180, 3, 82, 59, 238, 239, 79, 12, 189, 18, 178, 65, 73, 216, 56])

# Move mapping (0-17 internal representation)
MOVE_MAP = {
    0: "U", 1: "U'", 2: "R", 3: "R'", 4: "F", 5: "F'",
    6: "D", 7: "D'", 8: "L", 9: "L'", 10: "B", 11: "B'",
    12: "U2", 13: "R2", 14: "F2", 15: "D2", 16: "L2", 17: "B2"
}


# ============================================================================
# ENCRYPTION
# ============================================================================

class GanCubeEncrypter:
    """Simplified GAN Gen2 encryption/decryption"""
    
    def __init__(self, key: bytes, iv: bytes, mac_address: str):
        self.key = key
        self.iv = iv
        
        # Create salt from MAC address (reversed)
        # Handle different MAC formats
        if ':' in mac_address:
            mac_parts = mac_address.split(':')
        elif '-' in mac_address:
            mac_parts = mac_address.split('-')
        else:
            # Try to parse as continuous hex string
            mac_parts = [mac_address[i:i+2] for i in range(0, min(12, len(mac_address)), 2)]
        
        # Convert to bytes, handling potential errors
        try:
            mac_bytes = [int(x, 16) for x in mac_parts[:6]]  # Only take first 6 parts
        except (ValueError, IndexError):
            # Fallback to default salt if MAC parsing fails
            print(f"Warning: Could not parse MAC address '{mac_address}', using default salt")
            mac_bytes = [0xAB, 0x12, 0x34, 0x62, 0xBC, 0x15]
            
        self.salt = bytes(reversed(mac_bytes))
        
        # XOR key and IV with salt
        self.final_key = bytes(a ^ b for a, b in zip(self.key, self.salt * 3))[:16]
        self.final_iv = bytes(a ^ b for a, b in zip(self.iv, self.salt * 3))[:16]
        
    def decrypt(self, data: bytes) -> bytes:
        """Decrypt data from cube"""
        # Convert IV to counter for CTR mode
        iv_int = int.from_bytes(self.final_iv, byteorder='big')
        counter = Counter.new(128, initial_value=iv_int)
        
        cipher = AES.new(self.final_key, AES.MODE_CTR, counter=counter)
        return cipher.decrypt(data)
    
    def encrypt(self, data: bytes) -> bytes:
        """Encrypt data to cube"""
        iv_int = int.from_bytes(self.final_iv, byteorder='big')
        counter = Counter.new(128, initial_value=iv_int)
        
        cipher = AES.new(self.final_key, AES.MODE_CTR, counter=counter)
        return cipher.encrypt(data)


# ============================================================================
# DUPLICATE FILTER
# ============================================================================

class DuplicateFilter:
    """Filter duplicate moves from cube"""
    
    def __init__(self):
        self.last_move_data = None
        self.last_move_time = 0
        
    def is_duplicate_move(self, data: bytes) -> bool:
        """Check if this move is a duplicate"""
        now_ms = time.perf_counter_ns() // 1_000_000
        
        # Same move within 50ms = duplicate
        if data == self.last_move_data and (now_ms - self.last_move_time) < 50:
            return True
            
        self.last_move_data = data
        self.last_move_time = now_ms
        return False


# ============================================================================
# GAMEPAD BATCHER
# ============================================================================

class GamepadBatcher:
    """Batch gamepad updates to avoid calling update() too often"""
    
    def __init__(self, gamepad):
        self.gamepad = gamepad
        self.dirty = False
        self.current_orientation = None
        
        # Button state tracking for batching
        self.buttons_pressed = set()
        self.buttons_released = set()
        
    def update_orientation(self, x: float, y: float, z: float):
        """Update joystick position (doesn't call update)"""
        # Clamp values to valid range
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
        
    async def flush_loop(self):
        """Background task that flushes updates at 125Hz"""
        while True:
            if self.dirty:
                self.gamepad.update()
                self.dirty = False
                # Clear button tracking after update
                self.buttons_pressed.clear()
                self.buttons_released.clear()
            await asyncio.sleep(0.008)  # 125Hz


# ============================================================================
# MAIN CONTROLLER
# ============================================================================

class CubeControllerV2:
    """Direct BLE to Gamepad controller with minimal latency"""
    
    def __init__(self, config_path: str = "config.json"):
        # Load configuration
        self.config = self.load_config(config_path)
        
        # BLE connection
        self.client = None
        self.encrypter = None
        
        # Gamepad
        self.gamepad = vg.VX360Gamepad()
        self.batcher = GamepadBatcher(self.gamepad)
        
        # Filters and processors
        self.duplicate_filter = DuplicateFilter()
        self.last_move_serial = -1  # Track move serial to detect new moves
        
        # Performance monitoring
        self.last_orientation_time = 0
        self.last_move_time = 0
        self.orientation_count = 0
        self.move_count = 0
        self.start_time = 0
        
        print("V2 Cube Controller initialized")
        print(f"Loaded {len(self.config.get('move_mappings', {}))} move mappings")
        
    def load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from JSON file"""
        # Try V2 directory first, then parent directory
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
        return {
            "move_mappings": {
                "U": "gamepad_r1",
                "U'": "gamepad_b",
                "R": "gamepad_l2",
                "R'": "gamepad_combo_y+dpad_down",
                "F": "gamepad_dpad_right",
                "F'": "gamepad_dpad_left",
                "D": "gamepad_a",
                "D'": "gamepad_r2",
                "L": "gamepad_x",
                "L'": "gamepad_y",
                "B": "gamepad_combo_y+r1",
                "B'": "gamepad_r3"
            },
            "sensitivity": {
                "movement_sensitivity": 2.0,
                "spin_z_sensitivity": 1.5
            },
            "deadzone": {
                "general_deadzone": 0.1,
                "spin_deadzone": 0.085
            }
        }
        
    async def find_cube(self) -> tuple[str, str]:
        """Scan for GAN cube and return address and MAC"""
        print("Scanning for GAN cube...")
        
        devices = await BleakScanner.discover(timeout=5.0)
        print(f"Found {len(devices)} devices")
        
        for device in devices:
            # Look for GAN cube names
            if device.name and ('GAN' in device.name or 'GANi' in device.name):
                print(f"Found GAN cube: {device.name} at {device.address}")
                
                # Extract MAC from advertisement data if available
                mac = device.address
                if hasattr(device, 'details') and 'props' in device.details:
                    # Try to get manufacturer data for MAC
                    props = device.details['props']
                    if 'ManufacturerData' in props:
                        # MAC might be in manufacturer data
                        pass
                
                return device.address, mac
                
        raise RuntimeError("No GAN cube found. Make sure cube is on and in pairing mode.")
        
    async def connect_cube(self, address: Optional[str] = None):
        """Connect to cube via BLE"""
        # Find cube if no address provided
        if not address:
            address, mac = await self.find_cube()
        else:
            mac = address  # Use address as MAC if not found
            
        print(f"Connecting to cube at {address}...")
        
        # Create BLE client
        self.client = BleakClient(address)
        await self.client.connect()
        
        if not self.client.is_connected:
            raise RuntimeError("Failed to connect to cube")
            
        print("Connected to cube!")
        
        # Setup encryption
        self.encrypter = GanCubeEncrypter(GAN_ENCRYPTION_KEY, GAN_ENCRYPTION_IV, mac)
        
        # Find and subscribe to notifications
        services = self.client.services
        
        # Find the GAN service (might have different UUID format)
        gan_service = None
        for service in services:
            if GAN_GEN2_SERVICE.lower() in str(service.uuid).lower():
                gan_service = service
                break
                
        if not gan_service:
            # List all services for debugging
            print("Available services:")
            for service in services:
                print(f"  - {service.uuid}")
            raise RuntimeError("GAN Gen2 service not found on cube")
            
        # Debug: list all characteristics
        print(f"Found GAN service with {len(gan_service.characteristics)} characteristics:")
        for char in gan_service.characteristics:
            print(f"  - {char.uuid} (properties: {char.properties})")
        
        # Find state characteristic - it should have notify property
        state_char = None
        command_char = None
        
        for char in gan_service.characteristics:
            # State char is for notifications (has notify property)
            if 'notify' in char.properties:
                state_char = char
                print(f"Using {char.uuid} as state characteristic (has notify)")
            # Command char is for writing
            elif 'write' in char.properties or 'write-without-response' in char.properties:
                command_char = char
                print(f"Using {char.uuid} as command characteristic (has write)")
                
        if not state_char:
            raise RuntimeError("State characteristic not found (no characteristic with notify property)")
            
        # Store command char for later use
        self.command_char = command_char
            
        # Subscribe to state notifications
        await self.client.start_notify(state_char, self._handle_notification)
        
        print("Subscribed to cube notifications")
        
        # Request initial state
        await self._send_command(bytes([0x04] + [0] * 19))  # Request facelets
        await asyncio.sleep(0.1)
        await self._send_command(bytes([0x09] + [0] * 19))  # Request battery
        
        self.start_time = time.perf_counter()
        
    async def _send_command(self, command: bytes):
        """Send encrypted command to cube"""
        if not hasattr(self, 'command_char') or not self.command_char:
            print("Warning: Command characteristic not available")
            return
            
        encrypted = self.encrypter.encrypt(command)
        await self.client.write_gatt_char(self.command_char, encrypted)
        
    async def _handle_notification(self, sender, data: bytes):
        """Handle incoming data from cube - CRITICAL PATH"""
        start_ns = time.perf_counter_ns()
        
        # Decrypt inline
        decrypted = self.encrypter.decrypt(data)
        
        # Convert to bit string for proper parsing
        bits = ''.join(f'{byte:08b}' for byte in decrypted)
        
        # Parse message type (first 4 BITS, not first byte!)
        msg_type = int(bits[0:4], 2) if len(bits) >= 4 else 0
        
        if msg_type == 0x02:  # MOVE
            if not self.duplicate_filter.is_duplicate_move(decrypted):
                self._process_move_immediate(decrypted)
                self.move_count += 1
                
        elif msg_type == 0x01:  # ORIENTATION
            self._process_orientation_immediate(decrypted)
            self.orientation_count += 1
            
        elif msg_type == 0x04:  # FACELETS
            print(f"Received facelets update")
            
        elif msg_type == 0x05:  # HARDWARE
            print(f"Received hardware info")
            
        elif msg_type == 0x09:  # BATTERY
            # Battery level is in bits 4-11 (second byte)
            battery_bits = bits[4:12] if len(bits) >= 12 else '0'
            battery_level = int(battery_bits, 2) if battery_bits else 0
            print(f"Battery: {battery_level}%")
            
        # Track processing time (debug)
        latency_us = (time.perf_counter_ns() - start_ns) // 1000
        if latency_us > 5000:  # More than 5ms
            print(f"⚠️ Slow processing: {latency_us/1000:.1f}ms")
            
    def _process_move_immediate(self, data: bytes):
        """Process move event - NO ASYNC"""
        # Convert to bit string for proper parsing
        bits = ''.join(f'{byte:08b}' for byte in data)
        
        def get_bits(start, length):
            return int(bits[start:start + length], 2) if bits[start:start + length] else 0
        
        # Parse move data according to Gen2 protocol
        # Bits 4-11: serial number (we use this to detect new moves)
        serial = get_bits(4, 8)
        
        # Skip if this is an old move we've already processed
        if self.last_move_serial == -1:
            # First move, just record serial
            self.last_move_serial = serial
            return
            
        # Calculate how many new moves
        diff = (serial - self.last_move_serial) & 0xFF
        if diff == 0 or diff > 7:
            return  # No new moves or invalid
            
        self.last_move_serial = serial
        
        # For simplicity, just parse the most recent move
        # Bits 12-15: face, Bit 16: direction
        face = get_bits(12, 4)
        direction = get_bits(16, 1)
        
        # Convert face and direction to move string
        face_map = {0: "U", 1: "R", 2: "F", 3: "D", 4: "L", 5: "B"}
        face_str = face_map.get(face % 6, "?")
        
        if direction == 1:
            move = f"{face_str}'"
        else:
            move = face_str
            
        # Check for double moves (would need more complex parsing)
        # For now, just handle single moves
        
        print(f"Move: {move}")
        
        # Get action from config
        action = self.config.get('move_mappings', {}).get(move)
        if not action:
            return
            
        # Execute action through batcher
        self._execute_gamepad_action(action)
        
    def _process_orientation_immediate(self, data: bytes):
        """Process orientation event - NO ASYNC"""
        # Convert bytes to bit string for precise parsing
        bits = ''.join(f'{byte:08b}' for byte in data)
        
        def get_bits(start, length):
            """Extract bits from bit string"""
            return int(bits[start:start + length], 2) if bits[start:start + length] else 0
        
        # Parse quaternion from specific bit positions (Gen2 protocol)
        # Bits 4-19: qw, 20-35: qx, 36-51: qy, 52-67: qz
        qw_raw = get_bits(4, 16)
        qx_raw = get_bits(20, 16)
        qy_raw = get_bits(36, 16)
        qz_raw = get_bits(52, 16)
        
        # Convert to normalized quaternion (-1 to 1 range)
        # High bit is sign, lower 15 bits are magnitude
        qx = (1 - (qx_raw >> 15) * 2) * (qx_raw & 0x7FFF) / 0x7FFF
        qy = (1 - (qy_raw >> 15) * 2) * (qy_raw & 0x7FFF) / 0x7FFF
        qz = (1 - (qz_raw >> 15) * 2) * (qz_raw & 0x7FFF) / 0x7FFF
        qw = (1 - (qw_raw >> 15) * 2) * (qw_raw & 0x7FFF) / 0x7FFF
        
        # Quaternion to Euler angles for better joystick mapping
        import math
        
        # Calculate Euler angles from quaternion
        # Roll (x-axis rotation)
        sinr_cosp = 2 * (qw * qx + qy * qz)
        cosr_cosp = 1 - 2 * (qx * qx + qy * qy)
        roll = math.atan2(sinr_cosp, cosr_cosp)
        
        # Pitch (y-axis rotation) 
        sinp = 2 * (qw * qy - qz * qx)
        if abs(sinp) >= 1:
            pitch = math.copysign(math.pi / 2, sinp)  # Use 90 degrees if out of range
        else:
            pitch = math.asin(sinp)
        
        # Yaw (z-axis rotation)
        siny_cosp = 2 * (qw * qz + qx * qy)
        cosy_cosp = 1 - 2 * (qy * qy + qz * qz)
        yaw = math.atan2(siny_cosp, cosy_cosp)
        
        # Convert radians to normalized range (-1 to 1)
        roll_norm = roll / math.pi  # -1 to 1
        pitch_norm = pitch / (math.pi / 2)  # -1 to 1
        yaw_norm = yaw / math.pi  # -1 to 1
        
        # Apply sensitivity settings
        sensitivity = self.config.get('sensitivity', {})
        movement_sens = sensitivity.get('movement_sensitivity', 2.0)
        spin_sens = sensitivity.get('spin_z_sensitivity', 1.5)
        
        # Map to joystick axes
        # Left stick: tilt for movement
        joy_x = pitch_norm * movement_sens  # Forward/back tilt
        joy_y = roll_norm * movement_sens   # Left/right tilt
        
        # Right stick: rotation/spin
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
        
    def _execute_gamepad_action(self, action: str):
        """Execute gamepad action through batcher"""
        # Map button names to vgamepad constants
        button_map = {
            'gamepad_a': vg.XUSB_BUTTON.XUSB_GAMEPAD_A,
            'gamepad_b': vg.XUSB_BUTTON.XUSB_GAMEPAD_B,
            'gamepad_x': vg.XUSB_BUTTON.XUSB_GAMEPAD_X,
            'gamepad_y': vg.XUSB_BUTTON.XUSB_GAMEPAD_Y,
            'gamepad_r1': vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER,
            'gamepad_r2': None,  # Trigger, handled separately
            'gamepad_r3': vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB,
            'gamepad_l2': None,  # Trigger, handled separately
            'gamepad_dpad_up': vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP,
            'gamepad_dpad_down': vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN,
            'gamepad_dpad_left': vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT,
            'gamepad_dpad_right': vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT,
        }
        
        if action in button_map:
            button = button_map[action]
            if button:
                # Press and schedule release
                self.batcher.press_button(button)
                asyncio.create_task(self._delayed_release(button, 0.1))
                
        elif action == 'gamepad_r2':
            self.gamepad.right_trigger(255)
            self.batcher.dirty = True
            asyncio.create_task(self._delayed_trigger_release('right', 0.1))
            
        elif action == 'gamepad_l2':
            self.gamepad.left_trigger(255)
            self.batcher.dirty = True
            asyncio.create_task(self._delayed_trigger_release('left', 0.1))
            
        elif action.startswith('gamepad_combo_'):
            # Handle combos like Y+DpadDown
            asyncio.create_task(self._execute_combo(action))
            
    async def _delayed_release(self, button, delay: float):
        """Release button after delay"""
        await asyncio.sleep(delay)
        self.batcher.release_button(button)
        
    async def _delayed_trigger_release(self, side: str, delay: float):
        """Release trigger after delay"""
        await asyncio.sleep(delay)
        if side == 'right':
            self.gamepad.right_trigger(0)
        else:
            self.gamepad.left_trigger(0)
        self.batcher.dirty = True
        
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
            # Hold first, press second, release both
            self.batcher.press_button(button1)
            await asyncio.sleep(0.05)
            self.batcher.press_button(button2)
            await asyncio.sleep(0.1)
            self.batcher.release_button(button2)
            await asyncio.sleep(0.05)
            self.batcher.release_button(button1)
            
    async def print_stats_loop(self):
        """Print performance statistics periodically"""
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
            
            print("\n✅ V2 Controller ready! Move the cube to control gamepad.")
            print("Press Ctrl+C to exit.\n")
            
            # Run forever
            await asyncio.Future()
            
        except KeyboardInterrupt:
            print("\nShutting down...")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            # Cleanup
            if self.client:
                await self.client.disconnect()
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
        sys.exit(1)