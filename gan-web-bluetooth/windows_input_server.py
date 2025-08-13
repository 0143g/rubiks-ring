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

class WindowsInputServer:
    def __init__(self):
        self.active_keys = set()
        self.mouse_sensitivity = 2.0
        self.last_mouse_time = 0
        self.connected_clients = set()
        
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
        
        if move == "R":
            self.mouse_click("left")
            print("  ✅ Left Click → Windows")
        elif move == "R'":
            self.mouse_click("right")
            print("  ✅ Right Click → Windows")
        elif move == "L":
            self.key_press("a")
            print("  ✅ Key A → Windows")
        elif move == "L'":
            self.key_press("d")
            print("  ✅ Key D → Windows")
            
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
            
    def release_all_keys(self):
        """Release all currently pressed keys"""
        for key in list(self.active_keys):
            self.key_up(key)
        self.active_keys.clear()
        print("🔄 All keys released")

# Global server instance
server = WindowsInputServer()

async def handle_client(websocket, path):
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
    start_server = websockets.serve(handle_client, HOST, PORT)
    
    try:
        await start_server
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