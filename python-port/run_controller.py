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
    
    print(f"Starting controller bridge on {args.host}:{args.port}")
    print("Press Ctrl+C to stop")
    
    try:
        asyncio.run(server.start_server())
    except KeyboardInterrupt:
        print("\nController bridge stopped")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()