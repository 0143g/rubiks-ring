"""Example of connecting to and using a GAN Smart Cube."""

import asyncio
from gan_web_bluetooth import GanSmartCube, GanCubeMoveEvent


async def main():
    """Main example function."""
    cube = GanSmartCube()
    
    # Set up event handlers
    def on_move(event: GanCubeMoveEvent):
        print(f"Move: {event.move} (Face: {event.face}, Direction: {event.direction})")
    
    def on_facelets(event):
        print(f"Cube State: {event.facelets}")
        print(f"  CP: {event.state.CP}")
        print(f"  CO: {event.state.CO}")
        print(f"  EP: {event.state.EP}")
        print(f"  EO: {event.state.EO}")
    
    def on_orientation(event):
        q = event.quaternion
        print(f"Orientation: x={q.x:.3f}, y={q.y:.3f}, z={q.z:.3f}, w={q.w:.3f}")
        if event.angular_velocity:
            v = event.angular_velocity
            print(f"  Angular Velocity: x={v.x:.2f}, y={v.y:.2f}, z={v.z:.2f}")
    
    def on_battery(event):
        print(f"Battery: {event.percent}%")
    
    def on_hardware(event):
        print(f"Hardware Info:")
        print(f"  Model: {event.model}")
        print(f"  Firmware: {event.firmware}")
        print(f"  Protocol: {event.protocol}")
    
    def on_connected(_):
        print("Connected to cube!")
    
    def on_disconnected(_):
        print("Disconnected from cube!")
    
    # Register event handlers
    cube.on('move', on_move)
    cube.on('facelets', on_facelets)
    cube.on('orientation', on_orientation)
    cube.on('battery', on_battery)
    cube.on('hardware', on_hardware)
    cube.on('connected', on_connected)
    cube.on('disconnected', on_disconnected)
    
    try:
        # Connect to cube (will scan for available devices)
        print("Scanning for GAN Smart Cube...")
        await cube.connect()
        
        # Request initial information
        print("\nRequesting cube information...")
        await cube.request_battery()
        await asyncio.sleep(1)
        
        # Get current state
        print("\nRequesting cube state...")
        state = await cube.get_state()
        if state:
            print(f"Current state: {state}")
        
        # Wait for cube events
        print("\nListening for cube events (60 seconds)...")
        print("Try making some moves on the cube!")
        await asyncio.sleep(60)
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Disconnect
        print("\nDisconnecting...")
        await cube.disconnect()


if __name__ == "__main__":
    asyncio.run(main())