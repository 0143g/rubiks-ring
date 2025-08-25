#!/usr/bin/env python3
"""Test basic bleak functionality to isolate the issue."""

import asyncio
import sys

print(f"Python version: {sys.version}")
print(f"Python executable: {sys.executable}")

try:
    import bleak
    try:
        print(f"Bleak version: {bleak.__version__}")
    except AttributeError:
        print("Bleak imported successfully (version info not available)")
except ImportError as e:
    print(f"Error importing bleak: {e}")
    sys.exit(1)

from bleak import BleakClient, BleakScanner

async def test_basic():
    """Test basic BLE operations."""
    print("\n--- Testing BLE Scanner ---")
    try:
        devices = await BleakScanner.discover(timeout=2.0)
        print(f"Found {len(devices)} devices")
        
        # Find the GAN cube
        gan_cube = None
        for device in devices:
            if device.name and "GAN" in device.name:
                gan_cube = device
                print(f"Found GAN cube: {device.name} at {device.address}")
                break
        
        if not gan_cube:
            print("No GAN cube found")
            return
            
        print(f"\n--- Testing Connection ---")
        print(f"Connecting to {gan_cube.address}...")
        
        async with BleakClient(gan_cube.address) as client:
            print(f"Connected: {client.is_connected}")
            
            print("\n--- Testing Services ---")
            services = client.services
            print(f"Found {len(services)} services")
            
            for service in services:
                print(f"  Service: {service.uuid}")
                for char in service.characteristics:
                    print(f"    Characteristic: {char.uuid}")
                    print(f"      Properties: {char.properties}")
                    
    except Exception as e:
        print(f"Error: {e}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_basic())