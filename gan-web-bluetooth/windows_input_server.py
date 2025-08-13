#!/usr/bin/env python3
"""
Windows Input Server for GAN Cube Controller
Runs as WebSocket SERVER on Windows to receive commands from WSL browser
Run this on Windows host, connects directly to browser
"""

import asyncio
import websockets
import json
import time
import sys

try:
    import win32api
    import win32con
    print("✅ Windows input libraries loaded")
except ImportError:
    print("❌ ERROR: pywin32 not installed!")
    print("Run on Windows: pip install pywin32")
    sys.exit(1)

# Try to import virtual gamepad library
try:
    import vgamepad as vg
    print("✅ Virtual gamepad library loaded")
    GAMEPAD_AVAILABLE = True
except ImportError:
    print("⚠️ vgamepad not found - installing...")
    import subprocess
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "vgamepad"])
        import vgamepad as vg
        print("✅ Virtual gamepad library installed and loaded")
        GAMEPAD_AVAILABLE = True
    except Exception as e:
        print(f"❌ Could not install vgamepad: {e}")
        print("💡 Falling back to keyboard/mouse only")
        GAMEPAD_AVAILABLE = False

class WindowsInputServer:
    def __init__(self):
        self.active_keys = set()
        self.mouse_sensitivity = 2.0
        self.last_mouse_time = 0
        self.connected_clients = set()
        
        # Initialize virtual gamepad
        self.gamepad = None
        if GAMEPAD_AVAILABLE:
            try:
                self.gamepad = vg.VX360Gamepad()
                print("Virtual Xbox controller created!")
                print("   Games will see this as a real Xbox controller")
            except Exception as e:
                print(f"⚠️ Could not create virtual gamepad: {e}")
                self.gamepad = None
        
        # Virtual key code mapping
        self.key_map = {
            'a': 0x41, 'b': 0x42, 'c': 0x43, 'd': 0x44, 'e': 0x45, 'f': 0x46,
            'g': 0x47, 'h': 0x48, 'i': 0x49, 'j': 0x4A, 'k': 0x4B, 'l': 0x4C,
            'm': 0x4D, 'n': 0x4E, 'o': 0x4F, 'p': 0x50, 'q': 0x51, 'r': 0x52,
            's': 0x53, 't': 0x54, 'u': 0x55, 'v': 0x56, 'w': 0x57, 'x': 0x58,
            'y': 0x59, 'z': 0x5A,
            'space': win32con.VK_SPACE,
            'shift': win32con.VK_SHIFT,
            'ctrl': win32con.VK_CONTROL,
            'alt': win32con.VK_MENU,
            'tab': win32con.VK_TAB,
            'enter': win32con.VK_RETURN,
            'escape': win32con.VK_ESCAPE
        }
        
    def handle_message(self, data):
        """Process incoming WebSocket message from browser"""
        msg_type = data.get('type', '')
        
        if msg_type == 'MOVE':
            self.handle_cube_move(data)
        elif msg_type == 'ORIENTATION':
            self.handle_orientation(data)
        elif msg_type == 'KEY_PRESS':
            self.handle_key_press(data)
        elif msg_type == 'KEY_RELEASE':
            self.handle_key_release(data)
        elif msg_type == 'MOUSE_CLICK':
            self.handle_mouse_click(data)
        elif msg_type == 'MOUSE_MOVE':
            self.handle_mouse_move(data)
            
    def handle_cube_move(self, data):
        """Handle cube face moves"""
        move = data.get('move', '')
        print(f"🎮 Cube move: {move}")
        
        # Use gamepad buttons if available, fallback to keyboard/mouse
        if self.gamepad:
            if move == "R":
                self.gamepad_button_press(vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER)
                print("  ✅ Gamepad R1 (Right Bumper) → Windows")
            elif move == "R'":
                self.gamepad_trigger_press('right')
                print("  ✅ Gamepad R2 (Right Trigger) → Windows")
            elif move == "L":
                self.gamepad_button_press(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
                print("  ✅ Gamepad B Button → Windows")
            elif move == "L'":
                self.gamepad_button_press(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
                print("  ✅ Gamepad B Button → Windows")
            elif move == "D":
                self.gamepad_button_press(vg.XUSB_BUTTON.XUSB_GAMEPAD_X)
                print("  ✅ Gamepad X Button → Windows")
            elif move == "B":
                self.gamepad_button_press(vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB)
                print("  ✅ Gamepad R3 (Right Stick Press) → Windows")
                
    def handle_orientation(self, data):
        """Handle cube orientation for analog joystick control"""
        if not self.gamepad: return  # No gamepad available
            
        # Get tilt values from cube orientation
        tilt_x = data.get('tiltX', 0.0)  # Left/Right tilt
        tilt_y = data.get('tiltY', 0.0)  # Forward/Back tilt
        spin_z = data.get('spinZ', 0.0)  # Spin rotation (microwave/ballerina axis)
        
        # Convert to joystick range (-32768 to 32767)
        left_stick_x = max(-32768, min(32767, int(tilt_x * 32767)))
        left_stick_y = max(-32768, min(32767, int(tilt_y * 32767)))
        right_stick_x = max(-32768, min(32767, int(spin_z * 32767)))
        
        # Set analog stick positions
        self.gamepad.left_joystick(x_value=left_stick_x, y_value=left_stick_y)
        self.gamepad.right_joystick(x_value=right_stick_x, y_value=0)  # Only X-axis for camera
        self.gamepad.update()
        
        # Rate limit logging
        if abs(left_stick_x) > 1000 or abs(left_stick_y) > 1000 or abs(right_stick_x) > 1000:
            print(f"Left Stick: X={left_stick_x}, Y={left_stick_y} | Right Stick: X={right_stick_x}")
            
    def handle_key_press(self, data):
        """Handle continuous key press"""
        key = data.get('key', '').lower()
        if key not in self.active_keys:
            self.key_down(key)
            self.active_keys.add(key)
            print(f"⌨️ Key DOWN: {key.upper()}")
            
    def handle_key_release(self, data):
        """Handle key release"""
        key = data.get('key', '').lower()
        if key in self.active_keys:
            self.key_up(key)
            self.active_keys.remove(key)
            print(f"⌨️ Key UP: {key.upper()}")
            
    def handle_mouse_click(self, data):
        """Handle mouse clicks"""
        button = data.get('button', 'left')
        self.mouse_click(button)
        print(f"🖱️ Mouse {button.upper()} click → Windows")
        
    def handle_mouse_move(self, data):
        """Handle mouse movement with rate limiting"""
        current_time = time.time()
        if current_time - self.last_mouse_time < 0.016:  # 60 FPS limit
            return
            
        delta_x = int(data.get('deltaX', 0) * self.mouse_sensitivity)
        delta_y = int(data.get('deltaY', 0) * self.mouse_sensitivity)
        
        if delta_x != 0 or delta_y != 0:
            self.mouse_move_relative(delta_x, delta_y)
            self.last_mouse_time = current_time
            print(f"🖱️ Mouse → ({delta_x:+d}, {delta_y:+d})")
            
    # Windows input implementations
    def mouse_click(self, button):
        """Send Windows mouse click"""
        if button == "left":
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0)
        elif button == "right":
            win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0)
            win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0)
            
    def mouse_move_relative(self, dx, dy):
        """Move Windows mouse cursor relatively"""
        win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, dx, dy)
        
    def key_press(self, key):
        """Send single Windows key press"""
        self.key_down(key)
        # Use timer for release to avoid blocking
        asyncio.get_event_loop().call_later(0.05, lambda: self.key_up(key))
        
    def key_down(self, key):
        """Send Windows key down event"""
        vk_code = self.key_map.get(key.lower())
        if vk_code:
            win32api.keybd_event(vk_code, 0, 0, 0)
            
    def key_up(self, key):
        """Send Windows key up event"""
        vk_code = self.key_map.get(key.lower())
        if vk_code:
            win32api.keybd_event(vk_code, 0, win32con.KEYEVENTF_KEYUP, 0)
            
    def gamepad_button_press(self, button):
        """Press and release a gamepad button"""
        if not self.gamepad:
            return
            
        self.gamepad.press_button(button=button)
        self.gamepad.update()
        
        # Schedule button release after short delay
        import threading
        def release_button():
            time.sleep(0.1)  # 100ms press
            self.gamepad.release_button(button=button)
            self.gamepad.update()
        
        threading.Thread(target=release_button, daemon=True).start()
        
    def gamepad_trigger_press(self, trigger_side):
        """Press and release a gamepad trigger"""
        if not self.gamepad:
            return
            
        # Triggers use values from 0 to 255
        if trigger_side == 'right':
            self.gamepad.right_trigger(value=255)  # Full press
        elif trigger_side == 'left':
            self.gamepad.left_trigger(value=255)   # Full press
        
        self.gamepad.update()
        
        # Schedule trigger release after short delay
        import threading
        def release_trigger():
            time.sleep(0.1)  # 100ms press
            if trigger_side == 'right':
                self.gamepad.right_trigger(value=0)  # Release
            elif trigger_side == 'left':
                self.gamepad.left_trigger(value=0)   # Release
            self.gamepad.update()
        
        threading.Thread(target=release_trigger, daemon=True).start()
        
    def release_all_keys(self):
        """Release all currently pressed keys and reset gamepad"""
        for key in list(self.active_keys):
            self.key_up(key)
        self.active_keys.clear()
        
        # Reset gamepad to neutral state
        if self.gamepad:
            self.gamepad.reset()
            self.gamepad.update()
            print("🔄 All keys and gamepad reset")
        else:
            print("🔄 All keys released")

# Global server instance
server = WindowsInputServer()

async def handle_client(websocket):
    """Handle incoming WebSocket connections from browser"""
    client_addr = websocket.remote_address
    server.connected_clients.add(websocket)
    print(f"🔗 Browser connected from {client_addr}")
    print("✅ Ready to receive cube commands!")
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                server.handle_message(data)
            except json.JSONDecodeError as e:
                print(f"⚠️ Invalid JSON: {e}")
            except Exception as e:
                print(f"⚠️ Error processing: {e}")
                
    except websockets.exceptions.ConnectionClosed:
        print(f"🔌 Browser disconnected: {client_addr}")
    except Exception as e:
        print(f"❌ Connection error: {e}")
    finally:
        server.connected_clients.discard(websocket)
        if not server.connected_clients:
            server.release_all_keys()

async def main():
    PORT = 8082  # Different port to avoid conflicts
    HOST = "localhost"
    
    print("🖥️ GAN Cube → Windows Input Server")
    print(f"🚀 Starting WebSocket server on {HOST}:{PORT}")
    print("📋 Waiting for browser to connect...")
    print()
    
    # Start WebSocket server
    try:
        async with websockets.serve(handle_client, HOST, PORT):
            print(f"✅ Server started successfully on {HOST}:{PORT}")
            await asyncio.Future()  # Run forever
    except KeyboardInterrupt:
        print("\n👋 Server stopped by user")
    finally:
        server.release_all_keys()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
    except Exception as e:
        print(f"❌ Server error: {e}")
        input("Press Enter to exit...")
