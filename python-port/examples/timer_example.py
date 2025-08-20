"""Example of connecting to and using a GAN Smart Timer."""

import asyncio
from gan_web_bluetooth import GanSmartTimer, GanTimerState


async def main():
    """Main example function."""
    timer = GanSmartTimer()
    
    # Set up event handlers
    def on_state_change(event):
        state_names = {
            GanTimerState.IDLE: "IDLE",
            GanTimerState.HANDS_ON: "HANDS ON",
            GanTimerState.HANDS_OFF: "HANDS OFF",
            GanTimerState.GET_SET: "GET SET (Ready)",
            GanTimerState.RUNNING: "RUNNING",
            GanTimerState.STOPPED: "STOPPED",
            GanTimerState.FINISHED: "FINISHED",
            GanTimerState.DISCONNECT: "DISCONNECT"
        }
        
        state_name = state_names.get(event.state, f"UNKNOWN ({event.state})")
        print(f"Timer State: {state_name}")
        
        if event.recorded_time:
            print(f"  Recorded Time: {event.recorded_time}")
    
    def on_time_update(time):
        print(f"New Time Recorded: {time}")
    
    def on_connected(_):
        print("Connected to timer!")
    
    def on_disconnected(_):
        print("Disconnected from timer!")
    
    # Register event handlers
    timer.on('state_change', on_state_change)
    timer.on('time_update', on_time_update)
    timer.on('connected', on_connected)
    timer.on('disconnected', on_disconnected)
    
    try:
        # Connect to timer (will scan for available devices)
        print("Scanning for GAN Smart Timer...")
        await timer.connect()
        
        # Get recorded times
        print("\nGetting recorded times...")
        times = await timer.get_recorded_times()
        print(f"Display Time: {times.display_time}")
        print(f"Previous Times: {', '.join(str(t) for t in times.previous_times)}")
        
        # Wait for timer events
        print("\nListening for timer events (60 seconds)...")
        print("Try using the timer:")
        print("1. Place hands on timer (HANDS_ON)")
        print("2. Wait for green light (GET_SET)")
        print("3. Lift hands to start (RUNNING)")
        print("4. Touch to stop (STOPPED)")
        
        await asyncio.sleep(60)
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Disconnect
        print("\nDisconnecting...")
        await timer.disconnect()


if __name__ == "__main__":
    asyncio.run(main())