#!/usr/bin/env python3
"""
Clean cube event stream - shows only parsed events without encryption spam.
"""

import asyncio
import sys
import time
from datetime import datetime
import signal

# Add parent directory to path for imports
sys.path.insert(0, '.')

try:
    from bleak import BleakClient
except ImportError:
    print("Error: bleak not installed. Run: pip install bleak")
    sys.exit(1)

from gan_web_bluetooth import definitions as defs
from gan_web_bluetooth.encryption import GanGen2CubeEncrypter
from gan_web_bluetooth.protocols.gen2 import GanGen2Protocol


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


class CleanCubeStream:
    """Clean event stream for GAN Smart Cube - only shows parsed events."""
    
    def __init__(self, cube_address: str, cube_mac: str):
        self.cube_address = cube_address
        self.cube_mac = cube_mac
        self.client = None
        self.running = True
        self.move_count = 0
        self.orientation_count = 0
        
        # Set up encryption
        mac_bytes = [int(x, 16) for x in self.cube_mac.split(':')]
        salt = bytes(reversed(mac_bytes))
        
        # Use standard GAN Gen2 key
        key_data = defs.GAN_ENCRYPTION_KEYS[0]
        
        self.encrypter = GanGen2CubeEncrypter(
            bytes(key_data['key']),
            bytes(key_data['iv']),
            salt
        )
        
        self.protocol = GanGen2Protocol(self.encrypter)
        
    def _fix_move_string(self, face: int, direction: int) -> str:
        """Fix move string parsing."""
        face_names = ['U', 'R', 'F', 'D', 'L', 'B']
        
        if 0 <= face < 6:
            move = face_names[face]
            if direction == 1:
                move += "'"
            return move
        else:
            # Invalid face - probably parsing error
            return f"?{face}{'`' if direction else ''}"
    
    async def clean_notification_handler(self, sender, data: bytes):
        """Handle notifications and show only clean parsed events."""
        try:
            # Decrypt the data
            decrypted = self.encrypter.decrypt(data)
            
            # Parse with protocol
            events = self.protocol.decode_event(decrypted)
            
            if events:
                for event in events:
                    if hasattr(event, 'face') and hasattr(event, 'direction'):
                        # This is a move event
                        self.move_count += 1
                        move = self._fix_move_string(event.face, event.direction)
                        
                        # Only show valid moves (face 0-5)
                        if 0 <= event.face < 6:
                            print(f"{Colors.GREEN}[{format_timestamp()}] MOVE #{self.move_count}: "
                                  f"{Colors.BOLD}{move}{Colors.ENDC} "
                                  f"(face={event.face}, dir={event.direction}, serial={event.serial})")
                        
                    elif hasattr(event, 'quaternion'):
                        # This is orientation data
                        self.orientation_count += 1
                        if self.orientation_count % 30 == 0:  # Show every 30th orientation
                            q = event.quaternion
                            print(f"{Colors.BLUE}[{format_timestamp()}] ORIENTATION: "
                                  f"x={q.x:6.3f}, y={q.y:6.3f}, z={q.z:6.3f}, w={q.w:6.3f}{Colors.ENDC}")
                    
                    elif hasattr(event, 'facelets'):
                        # This is cube state
                        print(f"{Colors.YELLOW}[{format_timestamp()}] CUBE STATE: "
                              f"{event.facelets}{Colors.ENDC}")
                    
                    elif hasattr(event, 'percent'):
                        # This is battery
                        print(f"{Colors.CYAN}[{format_timestamp()}] BATTERY: "
                              f"{event.percent}%{Colors.ENDC}")
                    
                    elif hasattr(event, 'model'):
                        # This is hardware info
                        print(f"{Colors.CYAN}[{format_timestamp()}] HARDWARE: "
                              f"{event.model} (firmware {event.firmware}){Colors.ENDC}")
        
        except Exception as e:
            # Silently ignore parsing errors for clean output
            pass
    
    async def run(self):
        """Run the clean stream test."""
        print_header("GAN SMART CUBE - CLEAN EVENT STREAM")
        print(f"{Colors.YELLOW}Starting at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.ENDC}")
        print(f"{Colors.CYAN}Cube: {self.cube_address}{Colors.ENDC}")
        
        try:
            # Connect to cube
            print(f"\n{Colors.YELLOW}Connecting...{Colors.ENDC}")
            self.client = BleakClient(self.cube_address)
            await self.client.connect()
            
            if not self.client.is_connected:
                raise RuntimeError("Failed to connect to cube")
            
            print(f"{Colors.GREEN}✓ Connected and ready!{Colors.ENDC}")
            
            # Subscribe to state notifications
            await self.client.start_notify(
                defs.GAN_GEN2_STATE_CHARACTERISTIC,
                self.clean_notification_handler
            )
            
            # Send initial requests
            try:
                # Battery request
                battery_cmd = bytes([0x09] + [0x00] * 19)
                await self.client.write_gatt_char(
                    defs.GAN_GEN2_COMMAND_CHARACTERISTIC, 
                    self.encrypter.encrypt(battery_cmd)
                )
                await asyncio.sleep(0.5)
                
                # Hardware request
                hardware_cmd = bytes([0x05] + [0x00] * 19)
                await self.client.write_gatt_char(
                    defs.GAN_GEN2_COMMAND_CHARACTERISTIC, 
                    self.encrypter.encrypt(hardware_cmd)
                )
                await asyncio.sleep(0.5)
                
                # Facelets request
                facelets_cmd = bytes([0x04] + [0x00] * 19)
                await self.client.write_gatt_char(
                    defs.GAN_GEN2_COMMAND_CHARACTERISTIC, 
                    self.encrypter.encrypt(facelets_cmd)
                )
                await asyncio.sleep(0.5)
                
            except Exception as e:
                print(f"Note: Some commands failed: {e}")
            
            # Stream events
            print(f"\n{Colors.GREEN}{Colors.BOLD}🎲 CUBE IS LIVE! 🎲{Colors.ENDC}")
            print(f"{Colors.YELLOW}Make moves or rotate the cube to see events...{Colors.ENDC}")
            print(f"{Colors.YELLOW}Press Ctrl+C to stop{Colors.ENDC}\n")
            
            start_time = time.time()
            last_stats = time.time()
            
            while self.running:
                await asyncio.sleep(0.1)
                
                # Print stats every 15 seconds
                now_time = time.time()
                if now_time - last_stats > 15:
                    elapsed = now_time - start_time
                    print(f"\n{Colors.CYAN}📊 Stats: {self.move_count} moves, "
                          f"{self.orientation_count} orientations, "
                          f"{elapsed:.0f}s elapsed{Colors.ENDC}")
                    last_stats = now_time
            
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}Stopping...{Colors.ENDC}")
        except Exception as e:
            print(f"\n{Colors.RED}Error: {e}{Colors.ENDC}")
        finally:
            # Cleanup
            if self.client and self.client.is_connected:
                try:
                    await self.client.disconnect()
                except:
                    pass
            
            # Final stats
            elapsed = time.time() - start_time if 'start_time' in locals() else 0
            print(f"\n{Colors.HEADER}Session Complete{Colors.ENDC}")
            print(f"Total moves: {self.move_count}")
            print(f"Total orientations: {self.orientation_count}")
            print(f"Duration: {elapsed:.1f} seconds")
            if self.move_count > 0 and elapsed > 0:
                print(f"Move rate: {self.move_count/elapsed:.2f} moves/second")


async def main():
    """Main entry point."""
    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print(f"\n{Colors.YELLOW}Shutting down...{Colors.ENDC}")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Configuration
    CUBE_ADDRESS = "ab:12:34:62:bc:15"
    CUBE_MAC = "ab:12:34:62:bc:15"
    
    print(f"{Colors.HEADER}Clean Cube Stream{Colors.ENDC}")
    print(f"Address: {CUBE_ADDRESS}")
    print(f"This shows only successfully parsed events from your cube.")
    
    # Run stream
    stream = CleanCubeStream(CUBE_ADDRESS, CUBE_MAC)
    await stream.run()


if __name__ == "__main__":
    asyncio.run(main())
