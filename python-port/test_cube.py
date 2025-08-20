#!/usr/bin/env python3
"""
Test script for GAN Smart Cube connection.
Connects to a cube and streams all data to terminal with colored output.
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


def print_info(label: str, value: str, color: str = Colors.CYAN):
    """Print labeled information."""
    print(f"{Colors.BOLD}{label:20}{Colors.ENDC} {color}{value}{Colors.ENDC}")


def format_timestamp() -> str:
    """Get formatted timestamp."""
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


class CubeTest:
    """Test harness for GAN Smart Cube."""
    
    def __init__(self):
        self.cube = GanSmartCube()
        self.move_count = 0
        self.start_time = time.time()
        self.last_state = None
        self.running = True
        
    def on_move(self, event: GanCubeMoveEvent):
        """Handle move events."""
        self.move_count += 1
        
        # Map face numbers to colors
        face_colors = {
            0: Colors.CYAN,    # U - White
            1: Colors.RED,     # R - Red
            2: Colors.GREEN,   # F - Green
            3: Colors.YELLOW,  # D - Yellow
            4: Colors.BLUE,    # L - Orange (using blue)
            5: Colors.BLUE,    # B - Blue
        }
        
        face_names = ['U', 'R', 'F', 'D', 'L', 'B']
        face_name = face_names[event.face] if event.face < 6 else '?'
        direction = "'" if event.direction == 1 else ""
        
        color = face_colors.get(event.face, Colors.ENDC)
        
        print(f"\n{Colors.GREEN}[{format_timestamp()}] MOVE #{self.move_count}{Colors.ENDC}")
        print(f"  {color}{Colors.BOLD}{face_name}{direction}{Colors.ENDC} "
              f"(Face: {event.face}, Dir: {event.direction}, Serial: {event.serial})")
        
        if event.cube_timestamp:
            print(f"  Cube time: {event.cube_timestamp:.0f}ms")
    
    def on_facelets(self, event: GanCubeFaceletsEvent):
        """Handle facelets state events."""
        print(f"\n{Colors.YELLOW}[{format_timestamp()}] CUBE STATE{Colors.ENDC}")
        print(f"  Serial: {event.serial}")
        
        # Display facelets in a visual format
        if event.facelets:
            self.last_state = event.facelets
            print(f"  Facelets: {event.facelets}")
            
            # Visual cube net display
            self._display_cube_net(event.facelets)
        
        if event.state:
            print(f"  CP: {event.state.CP}")
            print(f"  CO: {event.state.CO}")
            print(f"  EP: {event.state.EP}")
            print(f"  EO: {event.state.EO}")
    
    def _display_cube_net(self, facelets: str):
        """Display cube net visualization."""
        if len(facelets) != 54:
            return
        
        # Map facelets to colors
        color_map = {
            'U': Colors.CYAN,    # White (using cyan)
            'R': Colors.RED,     # Red
            'F': Colors.GREEN,   # Green
            'D': Colors.YELLOW,  # Yellow
            'L': Colors.BLUE,    # Orange (using blue)
            'B': Colors.BLUE,    # Blue
        }
        
        def colored_face(char: str) -> str:
            color = color_map.get(char, Colors.ENDC)
            return f"{color}■{Colors.ENDC}"
        
        print("\n  Cube Net:")
        # Up face
        for i in range(3):
            print("        ", end="")
            for j in range(3):
                print(colored_face(facelets[i*3 + j]), end=" ")
            print()
        
        # Middle belt (L, F, R, B)
        for i in range(3):
            # L face
            for j in range(3):
                print(colored_face(facelets[36 + i*3 + j]), end=" ")
            print(" ", end="")
            # F face
            for j in range(3):
                print(colored_face(facelets[18 + i*3 + j]), end=" ")
            print(" ", end="")
            # R face
            for j in range(3):
                print(colored_face(facelets[9 + i*3 + j]), end=" ")
            print(" ", end="")
            # B face
            for j in range(3):
                print(colored_face(facelets[45 + i*3 + j]), end=" ")
            print()
        
        # Down face
        for i in range(3):
            print("        ", end="")
            for j in range(3):
                print(colored_face(facelets[27 + i*3 + j]), end=" ")
            print()
    
    def on_orientation(self, event: GanCubeOrientationEvent):
        """Handle orientation events."""
        q = event.quaternion
        
        # Only print every 10th orientation update to avoid spam
        if hasattr(self, '_orientation_count'):
            self._orientation_count += 1
        else:
            self._orientation_count = 0
        
        if self._orientation_count % 10 == 0:
            print(f"\n{Colors.BLUE}[{format_timestamp()}] ORIENTATION{Colors.ENDC}")
            print(f"  Quaternion: x={q.x:6.3f}, y={q.y:6.3f}, z={q.z:6.3f}, w={q.w:6.3f}")
            
            if event.angular_velocity:
                v = event.angular_velocity
                print(f"  Angular Vel: x={v.x:6.2f}, y={v.y:6.2f}, z={v.z:6.2f} rad/s")
    
    def on_battery(self, event: GanCubeBatteryEvent):
        """Handle battery events."""
        battery_color = Colors.GREEN
        if event.percent < 50:
            battery_color = Colors.YELLOW
        if event.percent < 20:
            battery_color = Colors.RED
        
        print(f"\n{Colors.CYAN}[{format_timestamp()}] BATTERY{Colors.ENDC}")
        print(f"  Level: {battery_color}{event.percent}%{Colors.ENDC}")
    
    def on_hardware(self, event: GanCubeHardwareEvent):
        """Handle hardware info events."""
        print(f"\n{Colors.CYAN}[{format_timestamp()}] HARDWARE INFO{Colors.ENDC}")
        print_info("  Model:", event.model)
        print_info("  Firmware:", event.firmware)
        print_info("  Protocol:", event.protocol)
    
    def on_connected(self, _):
        """Handle connection event."""
        print(f"\n{Colors.GREEN}{Colors.BOLD}✓ CONNECTED TO CUBE!{Colors.ENDC}")
    
    def on_disconnected(self, _):
        """Handle disconnection event."""
        print(f"\n{Colors.RED}{Colors.BOLD}✗ DISCONNECTED FROM CUBE{Colors.ENDC}")
        self.running = False
    
    async def run(self):
        """Run the test."""
        print_header("GAN SMART CUBE TEST")
        print(f"{Colors.YELLOW}Starting test at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.ENDC}")
        
        # Register all event handlers
        self.cube.on('move', self.on_move)
        self.cube.on('facelets', self.on_facelets)
        self.cube.on('orientation', self.on_orientation)
        self.cube.on('battery', self.on_battery)
        self.cube.on('hardware', self.on_hardware)
        self.cube.on('connected', self.on_connected)
        self.cube.on('disconnected', self.on_disconnected)
        
        try:
            # Scan and connect
            print(f"\n{Colors.YELLOW}Scanning for GAN Smart Cube...{Colors.ENDC}")
            print("Make sure your cube is turned on and nearby!")
            
            await self.cube.connect()
            
            # Request initial information
            print(f"\n{Colors.YELLOW}Requesting cube information...{Colors.ENDC}")
            
            await asyncio.sleep(0.5)
            await self.cube.request_battery()
            
            await asyncio.sleep(0.5)
            await self.cube.request_hardware_info()
            
            await asyncio.sleep(0.5)
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
                          f"Time: {elapsed:.0f}s, "
                          f"Rate: {self.move_count/elapsed:.2f} moves/s{Colors.ENDC}")
            
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
            print_info("Total moves:", str(self.move_count))
            print_info("Total time:", f"{elapsed:.1f} seconds")
            if self.move_count > 0:
                print_info("Average rate:", f"{self.move_count/elapsed:.2f} moves/s")
            if self.last_state:
                print_info("Final state:", self.last_state[:20] + "...")


async def main():
    """Main entry point."""
    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print(f"\n{Colors.YELLOW}Shutting down...{Colors.ENDC}")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Check for required dependencies
    try:
        import bleak
        import cryptography
        import numpy
    except ImportError as e:
        print(f"{Colors.RED}Missing dependency: {e}{Colors.ENDC}")
        print(f"{Colors.YELLOW}Install with: pip install -r requirements.txt{Colors.ENDC}")
        sys.exit(1)
    
    # Run test
    test = CubeTest()
    await test.run()


if __name__ == "__main__":
    # Check Python version
    if sys.version_info < (3, 8):
        print(f"{Colors.RED}Python 3.8+ required{Colors.ENDC}")
        sys.exit(1)
    
    # Run the test
    asyncio.run(main())