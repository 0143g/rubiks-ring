#!/usr/bin/env python3
"""
GAN Cube Gaming Controller Launcher
Starts the controller bridge server for gaming input
"""

import argparse
import asyncio
import sys
import platform
from controller_bridge import ControllerBridgeServer, ControllerConfig

def print_banner():
    """Print startup banner."""
    print("🎮" + "="*50)
    print("    GAN CUBE GAMING CONTROLLER BRIDGE")
    print("    Convert cube moves to gaming input")
    print("="*52)
    print(f"Platform: {platform.system()}")
    print(f"Python: {sys.version.split()[0]}")
    print()

def print_instructions():
    """Print usage instructions."""
    print("📋 SETUP INSTRUCTIONS:")
    print("1. Start this controller bridge server")
    print("2. Start the cube dashboard: python run_dashboard.py")
    print("3. Open the dashboard in your browser")
    print("4. Connect your GAN Smart Cube")
    print("5. Enable controller mode in dashboard")
    print("6. Start your game and enjoy cube control!")
    print()
    print("🎯 CONTROLLER MAPPINGS:")
    print("   R/R' moves  → Gamepad R1/R2 (or mouse clicks)")
    print("   L/L' moves  → Gamepad B button (or keys)")
    print("   U/D moves   → Gamepad Y/X buttons")
    print("   F/F' moves  → D-pad Left/Right")
    print("   B moves     → Right stick press")
    print("   Cube tilt   → Left analog stick (WASD keys)")
    print("   Cube spin   → Right analog stick (mouse look)")
    print()

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="GAN Cube Gaming Controller Bridge")
    parser.add_argument('--host', default='localhost', help='Server host (default: localhost)')
    parser.add_argument('--port', type=int, default=8083, help='Server port (default: 8083)')
    parser.add_argument('--mouse-sensitivity', type=float, default=2.0, 
                       help='Mouse sensitivity multiplier (default: 2.0)')
    parser.add_argument('--movement-sensitivity', type=float, default=1.0,
                       help='Movement sensitivity multiplier (default: 1.0)')
    parser.add_argument('--deadzone', type=float, default=0.1,
                       help='Deadzone for orientation input (default: 0.1)')
    parser.add_argument('--rate-limit', type=int, default=16,
                       help='Rate limit in milliseconds ~60 FPS (default: 16)')
    
    args = parser.parse_args()
    
    print_banner()
    print_instructions()
    
    # Create controller configuration
    config = ControllerConfig(
        mouse_sensitivity=args.mouse_sensitivity,
        movement_sensitivity=args.movement_sensitivity,
        deadzone=args.deadzone,
        rate_limit_ms=args.rate_limit
    )
    
    # Create and start server
    server = ControllerBridgeServer(port=args.port, host=args.host)
    server.controller.config = config
    
    print(f"🚀 Starting controller bridge on {args.host}:{args.port}")
    print("💡 Tip: Lower rate-limit for higher responsiveness (e.g., --rate-limit 8)")
    print("⏹️  Press Ctrl+C to stop")
    print()
    
    try:
        asyncio.run(server.start_server())
    except KeyboardInterrupt:
        print("\n👋 Controller bridge stopped")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()