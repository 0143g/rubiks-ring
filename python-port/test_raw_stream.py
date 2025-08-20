#!/usr/bin/env python3
"""
Raw Bluetooth data streaming test for GAN Smart Cube.
Shows all raw data coming from the cube to debug communication issues.
"""

import asyncio
import sys
import time
from datetime import datetime
from typing import Optional
import signal

# Add parent directory to path for imports
sys.path.insert(0, '.')

try:
    from bleak import BleakClient, BleakScanner, BLEDevice
    from bleak.backends.device import BLEDevice
    from bleak.backends.scanner import AdvertisementData
except ImportError:
    print("Error: bleak not installed. Run: pip install bleak")
    sys.exit(1)

from gan_web_bluetooth import definitions as defs


# ANSI color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header(text: str):
    """Print a colored header."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text:^60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")


def format_timestamp() -> str:
    """Get formatted timestamp."""
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def bytes_to_hex(data: bytes) -> str:
    """Convert bytes to hex string for display."""
    return ' '.join(f'{b:02x}' for b in data)


class RawCubeStream:
    """Raw data streaming test for GAN Smart Cube."""
    
    def __init__(self, cube_address: str):
        self.cube_address = cube_address
        self.client = None
        self.running = True
        self.data_count = 0
        
    async def raw_notification_handler(self, sender, data: bytes):
        """Handle raw notifications from any characteristic."""
        self.data_count += 1
        
        print(f"\n{Colors.GREEN}[{format_timestamp()}] RAW DATA #{self.data_count}{Colors.ENDC}")
        print(f"  {Colors.CYAN}From: {sender}{Colors.ENDC}")
        print(f"  {Colors.YELLOW}Length: {len(data)} bytes{Colors.ENDC}")
        print(f"  {Colors.BOLD}Hex: {bytes_to_hex(data)}{Colors.ENDC}")
        
        # Try to decode as ASCII for any readable content
        try:
            ascii_content = data.decode('ascii', errors='ignore')
            if ascii_content.strip():
                print(f"  ASCII: '{ascii_content}'")
        except:
            pass
        
        # Show individual bytes
        print(f"  Bytes: {list(data)}")
    
    async def run(self):
        """Run the raw streaming test."""
        print_header("GAN SMART CUBE RAW DATA STREAM")
        print(f"{Colors.YELLOW}Starting test at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.ENDC}")
        print(f"{Colors.CYAN}Cube Address: {self.cube_address}{Colors.ENDC}")
        
        try:
            # Connect to cube
            print(f"\n{Colors.YELLOW}Connecting to cube...{Colors.ENDC}")
            self.client = BleakClient(self.cube_address)
            await self.client.connect()
            
            if not self.client.is_connected:
                raise RuntimeError("Failed to connect to cube")
            
            print(f"{Colors.GREEN}✓ Connected!{Colors.ENDC}")
            
            # Get all services and characteristics
            print(f"\n{Colors.YELLOW}Discovering services and characteristics...{Colors.ENDC}")
            services = self.client.services
            
            all_characteristics = []
            for service in services:
                print(f"\n{Colors.CYAN}Service: {service.uuid}{Colors.ENDC}")
                for char in service.characteristics:
                    print(f"  Characteristic: {char.uuid}")
                    print(f"    Properties: {char.properties}")
                    
                    # Check if we can notify
                    if 'notify' in char.properties:
                        print(f"    {Colors.GREEN}✓ Supports notifications{Colors.ENDC}")
                        all_characteristics.append((service.uuid, char))
                    else:
                        print(f"    ✗ No notifications")
            
            # Subscribe to ALL characteristics that support notifications
            print(f"\n{Colors.YELLOW}Subscribing to all notification characteristics...{Colors.ENDC}")
            
            subscribed_count = 0
            for service_uuid, char in all_characteristics:
                try:
                    await self.client.start_notify(char, self.raw_notification_handler)
                    print(f"  ✓ Subscribed to {char.uuid}")
                    subscribed_count += 1
                except Exception as e:
                    print(f"  ✗ Failed to subscribe to {char.uuid}: {e}")
            
            print(f"\n{Colors.GREEN}Subscribed to {subscribed_count} characteristics{Colors.ENDC}")
            
            # Send some commands to trigger responses
            print(f"\n{Colors.YELLOW}Sending test commands...{Colors.ENDC}")
            
            # Find command characteristic (Gen2)
            command_char = None
            for service in services:
                if service.uuid.lower() == defs.GAN_GEN2_SERVICE.lower():
                    for char in service.characteristics:
                        if char.uuid.lower() == defs.GAN_GEN2_COMMAND_CHARACTERISTIC.lower():
                            command_char = char
                            break
            
            if command_char:
                print(f"Found command characteristic: {command_char.uuid}")
                
                # Send battery request (Gen2 format)
                try:
                    battery_cmd = bytes([0x09] + [0x00] * 19)  # Battery request
                    print(f"Sending battery request: {bytes_to_hex(battery_cmd)}")
                    await self.client.write_gatt_char(command_char, battery_cmd)
                    await asyncio.sleep(0.5)
                except Exception as e:
                    print(f"Error sending battery command: {e}")
                
                # Send hardware info request
                try:
                    hardware_cmd = bytes([0x05] + [0x00] * 19)  # Hardware request
                    print(f"Sending hardware request: {bytes_to_hex(hardware_cmd)}")
                    await self.client.write_gatt_char(command_char, hardware_cmd)
                    await asyncio.sleep(0.5)
                except Exception as e:
                    print(f"Error sending hardware command: {e}")
                
                # Send facelets request
                try:
                    facelets_cmd = bytes([0x04] + [0x00] * 19)  # Facelets request
                    print(f"Sending facelets request: {bytes_to_hex(facelets_cmd)}")
                    await self.client.write_gatt_char(command_char, facelets_cmd)
                    await asyncio.sleep(0.5)
                except Exception as e:
                    print(f"Error sending facelets command: {e}")
            else:
                print("No command characteristic found")
            
            # Stream data
            print(f"\n{Colors.GREEN}{Colors.BOLD}STREAMING RAW DATA{Colors.ENDC}")
            print(f"{Colors.YELLOW}Make moves on the cube or try rotating it!{Colors.ENDC}")
            print(f"{Colors.YELLOW}Press Ctrl+C to stop...{Colors.ENDC}")
            
            # Keep streaming
            start_time = time.time()
            while self.running:
                await asyncio.sleep(1)
                
                # Print periodic status
                elapsed = time.time() - start_time
                if int(elapsed) % 10 == 0 and int(elapsed) > 0:
                    print(f"\n{Colors.CYAN}[STATUS] Running for {elapsed:.0f}s, "
                          f"received {self.data_count} data packets{Colors.ENDC}")
            
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}Test interrupted by user{Colors.ENDC}")
        except Exception as e:
            print(f"\n{Colors.RED}Error: {e}{Colors.ENDC}")
            import traceback
            traceback.print_exc()
        finally:
            # Cleanup
            if self.client and self.client.is_connected:
                print(f"\n{Colors.YELLOW}Disconnecting...{Colors.ENDC}")
                try:
                    await self.client.disconnect()
                except:
                    pass
            
            # Final stats
            print_header("RAW STREAM COMPLETE")
            print(f"Total data packets received: {self.data_count}")


async def main():
    """Main entry point."""
    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print(f"\n{Colors.YELLOW}Shutting down...{Colors.ENDC}")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Configuration
    CUBE_ADDRESS = "ab:12:34:62:bc:15"  # Your cube's address
    
    print(f"{Colors.HEADER}Raw Data Stream Configuration:{Colors.ENDC}")
    print(f"  Cube Address: {CUBE_ADDRESS}")
    print(f"\n{Colors.YELLOW}This will show ALL raw data from your cube!{Colors.ENDC}")
    
    # Run test
    stream = RawCubeStream(CUBE_ADDRESS)
    await stream.run()


if __name__ == "__main__":
    # Check Python version
    if sys.version_info < (3, 8):
        print(f"{Colors.RED}Python 3.8+ required{Colors.ENDC}")
        sys.exit(1)
    
    # Run the test
    asyncio.run(main())