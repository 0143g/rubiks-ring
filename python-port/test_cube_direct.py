#!/usr/bin/env python3
"""
Direct connection test for GAN Smart Cube with known address.
Bypasses scanning and connects directly to the specified address.
"""

import asyncio
import sys
import time
from datetime import datetime
from typing import Optional
import signal

# Add parent directory to path for imports
sys.path.insert(0, '.')

from gan_web_bluetooth import (
    GanSmartCube,
    GanCubeMoveEvent,
    GanCubeFaceletsEvent,
    GanCubeOrientationEvent,
    GanCubeBatteryEvent,
    GanCubeHardwareEvent
)


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
    UNDERLINE = '\033[4m'


def print_header(text: str):
    """Print a colored header."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text:^60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")


def format_timestamp() -> str:
    """Get formatted timestamp."""
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


class DirectCubeTest:
    """Direct connection test for GAN Smart Cube."""
    
    def __init__(self, cube_address: str, cube_mac: str = None):
        self.cube_address = cube_address
        self.cube_mac = cube_mac
        self.cube = GanSmartCube()
        self.move_count = 0
        self.start_time = time.time()
        self.running = True
        
    def on_move(self, event: GanCubeMoveEvent):
        """Handle move events."""
        self.move_count += 1
        face_names = ['U', 'R', 'F', 'D', 'L', 'B']
        face_name = face_names[event.face] if event.face < 6 else '?'
        direction = "'" if event.direction == 1 else ""
        
        print(f"\n{Colors.GREEN}[{format_timestamp()}] MOVE #{self.move_count}{Colors.ENDC}")
        print(f"  {Colors.BOLD}{face_name}{direction}{Colors.ENDC} (Face: {event.face}, Dir: {event.direction})")
        
        if event.cube_timestamp:
            print(f"  Cube time: {event.cube_timestamp:.0f}ms")
    
    def on_facelets(self, event: GanCubeFaceletsEvent):
        """Handle facelets state events."""
        print(f"\n{Colors.YELLOW}[{format_timestamp()}] CUBE STATE{Colors.ENDC}")
        print(f"  Serial: {event.serial}")
        print(f"  Facelets: {event.facelets}")
    
    def on_orientation(self, event: GanCubeOrientationEvent):
        """Handle orientation events."""
        q = event.quaternion
        if hasattr(self, '_orientation_count'):
            self._orientation_count += 1
        else:
            self._orientation_count = 0
        
        if self._orientation_count % 20 == 0:  # Print every 20th update
            print(f"\n{Colors.BLUE}[{format_timestamp()}] ORIENTATION{Colors.ENDC}")
            print(f"  Quaternion: x={q.x:6.3f}, y={q.y:6.3f}, z={q.z:6.3f}, w={q.w:6.3f}")
    
    def on_battery(self, event: GanCubeBatteryEvent):
        """Handle battery events."""
        print(f"\n{Colors.CYAN}[{format_timestamp()}] BATTERY: {event.percent}%{Colors.ENDC}")
    
    def on_hardware(self, event: GanCubeHardwareEvent):
        """Handle hardware info events."""
        print(f"\n{Colors.CYAN}[{format_timestamp()}] HARDWARE INFO{Colors.ENDC}")
        print(f"  Model: {event.model}")
        print(f"  Firmware: {event.firmware}")
        print(f"  Protocol: {event.protocol}")
    
    def on_connected(self, _):
        """Handle connection event."""
        print(f"\n{Colors.GREEN}{Colors.BOLD}✓ CONNECTED TO CUBE!{Colors.ENDC}")
    
    def on_disconnected(self, _):
        """Handle disconnection event."""
        print(f"\n{Colors.RED}{Colors.BOLD}✗ DISCONNECTED FROM CUBE{Colors.ENDC}")
        self.running = False
    
    async def run(self):
        """Run the direct connection test."""
        print_header("GAN SMART CUBE DIRECT CONNECTION TEST")
        print(f"{Colors.YELLOW}Starting test at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.ENDC}")
        print(f"{Colors.CYAN}Cube Address: {self.cube_address}{Colors.ENDC}")
        if self.cube_mac:
            print(f"{Colors.CYAN}Cube MAC: {self.cube_mac}{Colors.ENDC}")
        
        # Register all event handlers
        self.cube.on('move', self.on_move)
        self.cube.on('facelets', self.on_facelets)
        self.cube.on('orientation', self.on_orientation)
        self.cube.on('battery', self.on_battery)
        self.cube.on('hardware', self.on_hardware)
        self.cube.on('connected', self.on_connected)
        self.cube.on('disconnected', self.on_disconnected)
        
        try:
            # Connect directly to known address
            print(f"\n{Colors.YELLOW}Connecting directly to cube at {self.cube_address}...{Colors.ENDC}")
            
            # If we have a MAC address, provide it
            if self.cube_mac:
                async def mac_provider(device_addr):
                    return self.cube_mac
                self.cube._mac_provider = mac_provider
            
            await self.cube.connect(device_address=self.cube_address)
            
            # Request initial information
            print(f"\n{Colors.YELLOW}Requesting cube information...{Colors.ENDC}")
            
            await asyncio.sleep(1)
            await self.cube.request_battery()
            
            await asyncio.sleep(1)
            await self.cube.request_hardware_info()
            
            await asyncio.sleep(1)
            print(f"\n{Colors.YELLOW}Requesting initial cube state...{Colors.ENDC}")
            state = await self.cube.get_state()
            
            # Main loop
            print(f"\n{Colors.GREEN}{Colors.BOLD}STREAMING CUBE DATA{Colors.ENDC}")
            print(f"{Colors.YELLOW}Make moves on the cube to see data!{Colors.ENDC}")
            print(f"{Colors.YELLOW}Press Ctrl+C to stop...{Colors.ENDC}")
            
            # Keep running until interrupted
            while self.running:
                await asyncio.sleep(1)
                
                # Print stats every 30 seconds
                elapsed = time.time() - self.start_time
                if int(elapsed) % 30 == 0 and int(elapsed) > 0:
                    print(f"\n{Colors.CYAN}[STATS] Moves: {self.move_count}, "
                          f"Time: {elapsed:.0f}s{Colors.ENDC}")
            
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}Test interrupted by user{Colors.ENDC}")
        except Exception as e:
            print(f"\n{Colors.RED}Error: {e}{Colors.ENDC}")
            import traceback
            traceback.print_exc()
        finally:
            # Cleanup
            print(f"\n{Colors.YELLOW}Disconnecting...{Colors.ENDC}")
            await self.cube.disconnect()
            
            # Final stats
            elapsed = time.time() - self.start_time
            print_header("TEST COMPLETE")
            print(f"Total moves: {self.move_count}")
            print(f"Total time: {elapsed:.1f} seconds")


async def main():
    """Main entry point."""
    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print(f"\n{Colors.YELLOW}Shutting down...{Colors.ENDC}")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Configuration - UPDATE THESE FOR YOUR CUBE
    CUBE_ADDRESS = "ab:12:34:62:bc:15"  # Your cube's Bluetooth address
    CUBE_MAC = "ab:12:34:62:bc:15"      # Your cube's MAC (often same as address)
    
    print(f"{Colors.HEADER}Configuration:{Colors.ENDC}")
    print(f"  Cube Address: {CUBE_ADDRESS}")
    print(f"  Cube MAC: {CUBE_MAC}")
    print(f"\n{Colors.YELLOW}Make sure these match your cube!{Colors.ENDC}")
    print(f"{Colors.YELLOW}You can find the address by scanning with your phone's Bluetooth settings.{Colors.ENDC}")
    
    # Run test
    test = DirectCubeTest(CUBE_ADDRESS, CUBE_MAC)
    await test.run()


if __name__ == "__main__":
    # Check Python version
    if sys.version_info < (3, 8):
        print(f"{Colors.RED}Python 3.8+ required{Colors.ENDC}")
        sys.exit(1)
    
    # Run the test
    asyncio.run(main())