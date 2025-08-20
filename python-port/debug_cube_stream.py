#!/usr/bin/env python3
"""
Debug script for GAN Smart Cube data stream.
Shows all raw encrypted and decrypted data coming from the cube.
"""

import asyncio
import sys
import time
from typing import Optional, Callable, List, Dict, Any, Union
from dataclasses import dataclass

try:
    from bleak import BleakClient, BleakScanner, BLEDevice
    from bleak.backends.device import BLEDevice
    from bleak.backends.scanner import AdvertisementData
except ImportError:
    print("Error: bleak library not found. Install with: pip install bleak")
    sys.exit(1)

from gan_web_bluetooth import definitions as defs
from gan_web_bluetooth.protocols.gen2 import GanGen2Protocol
from gan_web_bluetooth.encryption.encrypters import GanGen2CubeEncrypter
from gan_web_bluetooth.utils import now


class CubeStreamDebugger:
    """Debug utility to show raw cube data streams."""
    
    def __init__(self):
        self._client: Optional[BleakClient] = None
        self._protocol: Optional[GanGen2Protocol] = None
        self._connected = False
        self._command_char = None
        self._state_char = None
        self.packet_count = 0
    
    async def connect_and_debug(self, device_address: Optional[str] = None):
        """Connect to cube and start debugging data stream."""
        
        # Find device if no address provided
        device = None
        mac_address = None
        
        if not device_address:
            device, mac_address = await self._scan_for_cube()
            if not device:
                print("❌ No GAN Smart Cube found")
                return
            device_address = device.address
        
        print(f"🔍 Connecting to cube at {device_address}...")
        
        # Get MAC address for encryption
        if not mac_address:
            mac_address = await self._get_mac_from_scan(device_address)
        
        if not mac_address:
            print(f"⚠️ Warning: No MAC address found, using device address as fallback")
            mac_address = device_address
        
        print(f"🔑 Using MAC address: {mac_address}")
        
        # Create encryption salt from MAC (reversed)
        try:
            mac_bytes = [int(x, 16) for x in mac_address.split(':')]
            salt = bytes(reversed(mac_bytes))
            print(f"🧂 Encryption salt: {salt.hex()}")
        except:
            print(f"❌ Invalid MAC format: {mac_address}")
            return
        
        # Connect to device
        self._client = BleakClient(device_address)
        await self._client.connect()
        print(f"✅ Connected! Device is connected: {self._client.is_connected}")
        
        # Get services and detect protocol
        print("🔍 Discovering services...")
        services = self._client.services
        
        # Check for Gen2 protocol
        if services.get_service(defs.GAN_GEN2_SERVICE):
            print("✅ Found Gen2 service")
            service = services.get_service(defs.GAN_GEN2_SERVICE)
            self._command_char = service.get_characteristic(defs.GAN_GEN2_COMMAND_CHARACTERISTIC)
            self._state_char = service.get_characteristic(defs.GAN_GEN2_STATE_CHARACTERISTIC)
            
            # Setup encryption
            key_data = defs.GAN_ENCRYPTION_KEYS[0]  # Standard GAN key
            encrypter = GanGen2CubeEncrypter(
                bytes(key_data['key']),
                bytes(key_data['iv']),
                salt
            )
            self._protocol = GanGen2Protocol(encrypter)
            print("✅ Gen2 protocol configured with encryption")
        else:
            print("❌ No supported cube protocol found")
            await self._client.disconnect()
            return
        
        # Subscribe to state notifications
        print("📡 Starting data stream monitoring...")
        await self._client.start_notify(
            self._state_char,
            self._handle_raw_notification
        )
        
        self._connected = True
        
        # Send some initial commands to get data flowing
        print("\n🚀 Sending initial commands...")
        await self._send_command(0x05)  # Request hardware info
        await asyncio.sleep(0.5)
        await self._send_command(0x09)  # Request battery
        await asyncio.sleep(0.5)
        await self._send_command(0x04)  # Request facelets
        
        print("\n" + "="*60)
        print("📊 LIVE DATA STREAM (make moves on your cube!)")
        print("="*60)
        
        # Keep monitoring
        try:
            while self._connected:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n⏹️ Stopping debug session...")
    
    async def _send_command(self, command_byte: int):
        """Send raw command to cube."""
        if not self._protocol or not self._command_char:
            return
        
        # Create 20-byte command
        cmd_data = bytearray(20)
        cmd_data[0] = command_byte
        
        # Encrypt
        encrypted = self._protocol._encrypt(bytes(cmd_data))
        
        print(f"📤 Sending command: {command_byte:02X}")
        print(f"   Raw: {cmd_data.hex()}")
        print(f"   Encrypted: {encrypted.hex()}")
        
        await self._client.write_gatt_char(self._command_char, encrypted)
    
    def _handle_raw_notification(self, sender, data: bytes):
        """Handle raw notification and show detailed parsing."""
        self.packet_count += 1
        timestamp = now()
        
        print(f"\n📦 Packet #{self.packet_count} at {timestamp:.0f}ms")
        print(f"📥 Raw encrypted data ({len(data)} bytes): {data.hex()}")
        
        if not self._protocol:
            print("❌ No protocol configured")
            return
        
        # Decrypt the data
        try:
            decrypted = self._protocol._decrypt(data)
            print(f"🔓 Decrypted data: {decrypted.hex()}")
            
            # Show bit representation
            bit_str = ''.join(f'{byte:08b}' for byte in decrypted)
            print(f"🔢 Bit representation: {bit_str}")
            
            # Parse event type
            if len(decrypted) > 0:
                event_type = decrypted[0] & 0x0F  # First 4 bits
                print(f"📋 Event type: 0x{event_type:X}")
                
                if event_type == 0x01:
                    print("   Type: GYRO/ORIENTATION")
                    self._parse_gyro_event(decrypted)
                elif event_type == 0x02:
                    print("   Type: MOVE")
                    self._parse_move_event(decrypted)
                elif event_type == 0x04:
                    print("   Type: FACELETS")
                    self._parse_facelets_event(decrypted)
                elif event_type == 0x05:
                    print("   Type: HARDWARE")
                    self._parse_hardware_event(decrypted)
                elif event_type == 0x09:
                    print("   Type: BATTERY")
                    self._parse_battery_event(decrypted)
                elif event_type == 0x0D:
                    print("   Type: DISCONNECT")
                else:
                    print(f"   Type: UNKNOWN (0x{event_type:X})")
            
            # Try to decode using protocol
            events = self._protocol.decode_event(data)
            if events:
                print(f"✅ Decoded {len(events)} events:")
                for i, event in enumerate(events):
                    print(f"   Event {i+1}: {event}")
            else:
                print("⚠️ No events decoded")
                
        except Exception as e:
            print(f"❌ Decryption/parsing error: {e}")
            import traceback
            traceback.print_exc()
    
    def _parse_gyro_event(self, data: bytes):
        """Parse gyroscope event details."""
        if len(data) < 9:
            return
        
        from gan_web_bluetooth.protocols.gen2 import ProtocolMessageView
        msg = ProtocolMessageView(data)
        
        qw = msg.get_bit_word(4, 16)
        qx = msg.get_bit_word(20, 16) 
        qy = msg.get_bit_word(36, 16)
        qz = msg.get_bit_word(52, 16)
        
        print(f"   Quaternion raw: w={qw}, x={qx}, y={qy}, z={qz}")
    
    def _parse_move_event(self, data: bytes):
        """Parse move event details."""
        if len(data) < 3:
            return
            
        from gan_web_bluetooth.protocols.gen2 import ProtocolMessageView
        msg = ProtocolMessageView(data)
        
        serial = msg.get_bit_word(4, 8)
        print(f"   Serial: {serial}")
        
        # Parse moves
        for i in range(7):  # Max 7 moves in buffer
            if 12 + 5 * i + 5 <= len(data) * 8:
                face = msg.get_bit_word(12 + 5 * i, 4)
                direction = msg.get_bit_word(16 + 5 * i, 1)
                if face < 6:
                    move = "URFDLB"[face] + ("'" if direction else "")
                    print(f"   Move {i}: {move} (face={face}, dir={direction})")
    
    def _parse_facelets_event(self, data: bytes):
        """Parse facelets event details."""
        if len(data) < 14:
            return
            
        from gan_web_bluetooth.protocols.gen2 import ProtocolMessageView
        msg = ProtocolMessageView(data)
        
        serial = msg.get_bit_word(4, 8)
        print(f"   Serial: {serial}")
        
        # Parse some corner positions
        cp = []
        for i in range(7):
            cp.append(msg.get_bit_word(12 + i * 3, 3))
        print(f"   Corner permutation (7): {cp}")
    
    def _parse_hardware_event(self, data: bytes):
        """Parse hardware event details."""
        if len(data) < 14:
            return
            
        from gan_web_bluetooth.protocols.gen2 import ProtocolMessageView
        msg = ProtocolMessageView(data)
        
        hw_major = msg.get_bit_word(8, 8)
        hw_minor = msg.get_bit_word(16, 8)
        sw_major = msg.get_bit_word(24, 8)
        sw_minor = msg.get_bit_word(32, 8)
        
        print(f"   Hardware: {hw_major}.{hw_minor}")
        print(f"   Software: {sw_major}.{sw_minor}")
    
    def _parse_battery_event(self, data: bytes):
        """Parse battery event details."""
        if len(data) < 2:
            return
            
        from gan_web_bluetooth.protocols.gen2 import ProtocolMessageView
        msg = ProtocolMessageView(data)
        
        battery = msg.get_bit_word(8, 8)
        print(f"   Battery level: {battery}%")
    
    async def _scan_for_cube(self) -> tuple[Optional[BLEDevice], Optional[str]]:
        """Scan for GAN Smart Cube device."""
        print("🔍 Scanning for devices...")
        
        devices = await BleakScanner.discover(timeout=10.0)
        print(f"Found {len(devices)} devices:")
        
        for device in devices:
            name = device.name or "Unknown"
            print(f"  {device.address}: {name}")
            
            if device.name and any(
                device.name.startswith(prefix)
                for prefix in ["GAN", "MG", "AiCube"]
            ):
                print(f"✅ Found GAN cube: {device.name} at {device.address}")
                return device, device.address
        
        return None, None
    
    async def _get_mac_from_scan(self, device_address: str) -> Optional[str]:
        """Try to get MAC address from advertisement scan."""
        mac_address = None
        
        def detection_callback(device: BLEDevice, advertisement_data: AdvertisementData):
            nonlocal mac_address
            
            if device.address == device_address:
                if advertisement_data.manufacturer_data:
                    mac_address = defs.extract_mac_from_manufacturer_data(
                        advertisement_data.manufacturer_data
                    )
                    if mac_address:
                        return True
            return False
        
        # Scan for a short time to get manufacturer data
        await BleakScanner.find_device_by_filter(
            detection_callback,
            timeout=5.0
        )
        
        return mac_address
    
    async def disconnect(self):
        """Disconnect from cube."""
        if self._connected and self._client:
            try:
                if self._state_char:
                    await self._client.stop_notify(self._state_char)
                await self._client.disconnect()
            except:
                pass
            self._connected = False
            print("🔌 Disconnected from cube")


async def main():
    """Main debug function."""
    print("🧪 GAN Smart Cube Data Stream Debugger")
    print("=" * 50)
    print("This tool shows all raw encrypted and decrypted data")
    print("coming from your cube in real-time.")
    print()
    
    debugger = CubeStreamDebugger()
    
    try:
        await debugger.connect_and_debug()
    except KeyboardInterrupt:
        print("\n⏹️ Interrupted by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await debugger.disconnect()


if __name__ == "__main__":
    asyncio.run(main())