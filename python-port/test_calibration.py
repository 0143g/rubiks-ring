#!/usr/bin/env python3
"""
Test script to verify cube calibration and control mapping
"""

import asyncio
import json
import websockets
import time

async def test_calibration():
    """Connect to the dashboard WebSocket and monitor calibration data"""
    uri = "ws://localhost:5000/socket.io/?EIO=4&transport=websocket"
    
    print("Connecting to dashboard WebSocket...")
    print("-" * 50)
    print("CALIBRATION TEST INSTRUCTIONS:")
    print("1. Start the cube dashboard: python cube_dashboard.py")
    print("2. Connect your cube via the dashboard")
    print("3. Place cube with GREEN face forward, WHITE on top")
    print("4. Click 'Calibrate Cube' button in dashboard")
    print("5. Move the cube and observe the values below")
    print("-" * 50)
    
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected to dashboard!")
            
            # Send initial ping to establish connection
            await websocket.send('2probe')
            response = await websocket.recv()
            
            if response == '3probe':
                await websocket.send('5')  # Upgrade to Socket.IO
            
            print("\nMonitoring orientation data...")
            print("When calibrated at rest position, values should be near (0,0,0,1)")
            print("Format: CAL(x,y,z,w) | Movement(X,Y) | Spin(Z)")
            print("-" * 50)
            
            last_print_time = 0
            
            while True:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=0.1)
                    
                    # Parse Socket.IO message format
                    if message.startswith('42'):
                        # Extract JSON from Socket.IO message
                        json_str = message[2:]  # Remove '42' prefix
                        data = json.loads(json_str)
                        
                        if isinstance(data, list) and len(data) > 1:
                            event_name = data[0]
                            event_data = data[1]
                            
                            current_time = time.time()
                            
                            # Only print orientation updates every 500ms to reduce spam
                            if event_name == 'orientation' and current_time - last_print_time > 0.5:
                                if 'calibrated_quaternion' in event_data:
                                    cal = event_data['calibrated_quaternion']
                                    
                                    # Calculate approximate tilt values for debugging
                                    tilt_y = cal['x'] * 2  # Forward/back
                                    tilt_x = -cal['y'] * 2  # Left/right
                                    spin_z = cal['z'] * 2  # Rotation
                                    
                                    print(f"CAL({cal['x']:6.3f}, {cal['y']:6.3f}, {cal['z']:6.3f}, {cal['w']:6.3f}) | "
                                          f"Move(X:{tilt_x:5.2f}, Y:{tilt_y:5.2f}) | Spin(Z:{spin_z:5.2f})")
                                    
                                    # Check if calibration is working correctly
                                    if abs(cal['x']) < 0.05 and abs(cal['y']) < 0.05 and abs(cal['z']) < 0.05 and abs(cal['w'] - 1.0) < 0.05:
                                        print("  ✅ Cube is at calibrated rest position!")
                                    
                                    last_print_time = current_time
                                elif not event_data.get('is_calibrated', False):
                                    print("⚠️  Cube not calibrated yet - use 'Calibrate Cube' button")
                            
                            elif event_name == 'message':
                                msg_type = event_data.get('type', '')
                                msg_text = event_data.get('text', '')
                                if 'calibrated' in msg_text.lower():
                                    print(f"\n🎯 {msg_text}\n")
                
                except asyncio.TimeoutError:
                    continue
                except json.JSONDecodeError:
                    continue
                    
    except KeyboardInterrupt:
        print("\nTest stopped")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("Cube Calibration Test Tool")
    print("=" * 50)
    asyncio.run(test_calibration())