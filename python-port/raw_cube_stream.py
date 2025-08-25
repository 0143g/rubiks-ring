#!/usr/bin/env python3
import asyncio
import time
from gan_web_bluetooth import GanSmartCube

async def stream_raw_data():
    print("Creating GAN Smart Cube instance...")
    cube = GanSmartCube()
    
    message_count = 0
    last_print_time = time.time()
    connected = False
    
    # Hook into raw data events
    def handle_any_event(event):
        nonlocal message_count, last_print_time
        message_count += 1
        
        # Print event type and timestamp
        event_type = type(event).__name__
        print(f"[{time.time():.3f}] Event: {event_type}")
        
        # Every second, print stats
        current_time = time.time()
        if current_time - last_print_time >= 1.0:
            elapsed = current_time - last_print_time
            rate = message_count / elapsed
            print(f"--- Rate: {rate:.1f} msg/sec ---")
            message_count = 0
            last_print_time = current_time
    
    def handle_connected(event):
        nonlocal connected
        connected = True
        print("✅ Connected to cube!")
    
    def handle_disconnected(event):
        nonlocal connected
        connected = False
        print("❌ Disconnected from cube")
    
    # Register event handlers for all event types
    cube.on('move', handle_any_event)
    cube.on('facelets', handle_any_event)
    cube.on('orientation', handle_any_event)
    cube.on('battery', handle_any_event)
    cube.on('hardware', handle_any_event)
    cube.on('connected', handle_connected)
    cube.on('disconnected', handle_disconnected)
    
    print("Scanning for cube...")
    
    try:
        # Connect to cube (will scan automatically)
        await cube.connect()
        
        print("Streaming data. Press Ctrl+C to stop...")
        
        # Keep running until interrupted
        while connected:
            await asyncio.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\nStopping...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if connected:
            await cube.disconnect()
        print("Exited")

if __name__ == "__main__":
    try:
        asyncio.run(stream_raw_data())
    except KeyboardInterrupt:
        print("\nExiting...")