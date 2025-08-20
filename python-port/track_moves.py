#!/usr/bin/env python3
"""
Simple move tracker for GAN Smart Cube.
Only shows face turns (R, U, F, etc.) - filters out all the quaternion noise.
"""

import asyncio
import sys
from typing import Optional

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


class SimpleMoveTracker:
    """Simple move tracker that only shows face turns."""
    
    def __init__(self):
        self._client: Optional[BleakClient] = None
        self._protocol: Optional[GanGen2Protocol] = None
        self._connected = False
        self._command_char = None
        self._state_char = None
        self.move_count = 0
        self.last_state = None
    
    async def start_tracking(self, device_address: Optional[str] = None):
        """Start tracking moves."""
        
        # Find device if no address provided
        device = None
        mac_address = None
        
        if not device_address:
            device, mac_address = await self._scan_for_cube()
            if not device:
                print("❌ No GAN Smart Cube found")
                return
            device_address = device.address
        
        print(f"🎯 Connecting to cube: {device.name if device else device_address}")
        
        # Get MAC address for encryption
        if not mac_address:
            mac_address = await self._get_mac_from_scan(device_address)
        
        if not mac_address:
            print(f"⚠️ Using device address as MAC fallback")
            mac_address = device_address
        
        # Create encryption salt from MAC (reversed)
        try:
            mac_bytes = [int(x, 16) for x in mac_address.split(':')]
            salt = bytes(reversed(mac_bytes))
        except:
            print(f"❌ Invalid MAC format: {mac_address}")
            return
        
        # Connect to device
        self._client = BleakClient(device_address)
        await self._client.connect()
        print(f"✅ Connected!")
        
        # Get services and setup Gen2 protocol
        services = self._client.services
        
        if services.get_service(defs.GAN_GEN2_SERVICE):
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
            print("✅ Gen2 protocol ready")
        else:
            print("❌ No Gen2 service found")
            await self._client.disconnect()
            return
        
        # Subscribe to notifications
        await self._client.start_notify(
            self._state_char,
            self._handle_notification
        )
        
        self._connected = True
        
        # Request initial state to get synchronized
        await self._send_facelets_request()
        
        print("\n" + "="*50)
        print("🎲 MOVE TRACKER READY")
        print("Make some moves on your cube!")
        print("="*50)
        
        # Keep monitoring
        try:
            while self._connected:
                await asyncio.sleep(0.1)
        except KeyboardInterrupt:
            print("\n⏹️ Stopping move tracker...")
    
    async def _send_facelets_request(self):
        """Request current facelets state."""
        if not self._protocol or not self._command_char:
            return
        
        # Create facelets request command
        cmd_data = bytearray(20)
        cmd_data[0] = 0x04  # REQUEST_FACELETS
        
        # Encrypt and send
        encrypted = self._protocol._encrypt(bytes(cmd_data))
        await self._client.write_gatt_char(self._command_char, encrypted)
    
    def _handle_notification(self, sender, data: bytes):
        """Handle notifications and filter for moves only."""
        if not self._protocol:
            return
        
        try:
            # Decode events
            events = self._protocol.decode_event(data)
            if not events:
                return
            
            for event in events:
                # Only process move and facelets events
                if hasattr(event, 'type'):
                    if event.type == "MOVE":
                        self.move_count += 1
                        print(f"🎯 Move #{self.move_count}: {event.move}")
                        
                    elif event.type == "FACELETS":
                        if self.last_state is None:
                            print(f"📋 Initial cube state received (serial: {event.serial})")
                            self.last_state = event.facelets
                        else:
                            # State changed - this might indicate a move
                            if event.facelets != self.last_state:
                                print(f"📋 State changed (serial: {event.serial})")
                                self.last_state = event.facelets
                                
        except Exception as e:
            # Silently ignore parsing errors to keep output clean
            pass
    
    async def _scan_for_cube(self) -> tuple[Optional[BLEDevice], Optional[str]]:
        """Scan for GAN Smart Cube device."""
        print("🔍 Scanning for GAN cubes...")
        
        devices = await BleakScanner.discover(timeout=10.0)
        
        # Look for GAN cube by name
        for device in devices:
            if device.name and any(
                device.name.startswith(prefix)
                for prefix in ["GAN", "MG", "AiCube"]
            ):
                print(f"✅ Found: {device.name}")
                return device, device.address
        
        print("❌ No GAN cube found in scan")
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
        
        # Quick scan for manufacturer data
        await BleakScanner.find_device_by_filter(
            detection_callback,
            timeout=3.0
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
            print("🔌 Disconnected")


async def main():
    """Main tracking function."""
    print("🎲 GAN Smart Cube Move Tracker")
    print("=" * 40)
    print("This tool only shows face turns (R, U, F, etc.)")
    print("No quaternion spam - just clean move detection!")
    print()
    
    tracker = SimpleMoveTracker()
    
    try:
        await tracker.start_tracking()
    except KeyboardInterrupt:
        print("\n⏹️ Interrupted by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await tracker.disconnect()


if __name__ == "__main__":
    asyncio.run(main())