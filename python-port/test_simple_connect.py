#!/usr/bin/env python3
"""Simple test to find the slice error."""

import asyncio
from bleak import BleakClient, BleakScanner

async def test_connect():
    print("Scanning for GAN cube...")
    devices = await BleakScanner.discover(timeout=5.0)
    
    gan_cube = None
    for device in devices:
        if device.name and "GAN" in device.name:
            gan_cube = device
            print(f"Found: {device.name} at {device.address}")
            break
    
    if not gan_cube:
        print("No GAN cube found")
        return
    
    print(f"\nConnecting to {gan_cube.address}...")
    try:
        async with BleakClient(gan_cube.address) as client:
            print(f"Connected: {client.is_connected}")
            
            # Get services
            services = client.services
            print(f"Found {len(services)} services")
            
            # Find Gen2 service
            gen2_service_uuid = "6e400001-b5a3-f393-e0a9-e50e24dc4179"
            gen2_state_char_uuid = "28be4cb6-cd67-11e9-a32f-2a2ae2dbcce4"
            
            service = services.get_service(gen2_service_uuid)
            if service:
                print(f"Found Gen2 service")
                
                # Try to get the characteristic
                state_char = service.get_characteristic(gen2_state_char_uuid)
                if state_char:
                    print(f"Found state characteristic: {state_char}")
                    
                    # Try to subscribe to notifications
                    print("Attempting to subscribe to notifications...")
                    
                    def notification_handler(sender, data):
                        print(f"Notification from {sender}: {data.hex()}")
                    
                    await client.start_notify(state_char, notification_handler)
                    print("Successfully subscribed to notifications")
                    
                    # Wait a bit
                    await asyncio.sleep(2)
                    
                    await client.stop_notify(state_char)
                    print("Stopped notifications")
                else:
                    print("State characteristic not found")
            else:
                print("Gen2 service not found")
                
    except Exception as e:
        print(f"Error: {e}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_connect())