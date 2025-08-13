#!/usr/bin/env python3
"""
Windows Input Bridge for WSL GAN Cube Controller
Connects to WSL WebSocket and provides real Windows input
Run this on Windows host, not in WSL!
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

class WindowsInputBridge:
    def __init__(self):
        self.active_keys = set()
        self.mouse_sensitivity = 2.0
        self.last_mouse_time = 0
        
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
        """Process incoming WebSocket message"""
        msg_type = data.get('type', '')
        
        if msg_type == 'MOVE':
            self.handle_cube_move(data)
        elif msg_type == 'GYRO':
            # Could process orientation here if needed
            pass
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
            print("  → Left Click sent to Windows")
        elif move == "R'":
            self.mouse_click("right")
            print("  → Right Click sent to Windows")
        elif move == "L":
            self.key_press("a")
            print("  → Key A sent to Windows")
        elif move == "L'":
            self.key_press("d")
            print("  → Key D sent to Windows")
            
    def handle_key_press(self, data):
        """Handle continuous key press"""
        key = data.get('key', '').lower()
        if key not in self.active_keys:
            self.key_down(key)
            self.active_keys.add(key)
            print(f"⌨️ Key pressed: {key.upper()}")
            
    def handle_key_release(self, data):
        """Handle key release"""
        key = data.get('key', '').lower()
        if key in self.active_keys:
            self.key_up(key)
            self.active_keys.remove(key)
            print(f"⌨️ Key released: {key.upper()}")
            
    def handle_mouse_click(self, data):
        """Handle mouse clicks"""
        button = data.get('button', 'left')
        self.mouse_click(button)
        print(f"🖱️ Mouse {button} click sent to Windows")
        
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
            print(f"🖱️ Mouse moved: ({delta_x}, {delta_y})")
            
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
        time.sleep(0.05)  # 50ms press
        self.key_up(key)
        
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

# WebSocket client to connect to WSL server
async def connect_to_wsl():
    # Connect to your existing WSL WebSocket server
    WSL_HOST = "localhost"  # or your WSL IP
    WSL_PORT = 8080        # Your existing WSL port
    
    bridge = WindowsInputBridge()
    
    print(f"🔗 Connecting to WSL WebSocket at {WSL_HOST}:{WSL_PORT}")
    
    try:
        async with websockets.connect(f"ws://{WSL_HOST}:{WSL_PORT}") as websocket:
            print("✅ Connected to WSL! Windows input bridge active.")
            print("🎮 Cube moves will now control Windows games!")
            
            async for message in websocket:
                try:
                    data = json.loads(message)
                    bridge.handle_message(data)
                except json.JSONDecodeError as e:
                    print(f"⚠️ JSON decode error: {e}")
                except Exception as e:
                    print(f"⚠️ Error processing message: {e}")
                    
    except websockets.exceptions.ConnectionRefused:
        print(f"❌ Could not connect to WSL WebSocket at {WSL_HOST}:{WSL_PORT}")
        print("📋 Make sure your WSL WebSocket server is running!")
        print("📋 In WSL: Open simple-bridge.html and click 'Connect to WSL'")
    except Exception as e:
        print(f"❌ Connection error: {e}")
    finally:
        bridge.release_all_keys()
        print("🔌 Windows input bridge disconnected")

if __name__ == "__main__":
    print("🖥️ GAN Cube → Windows Input Bridge")
    print("📋 This bridges WSL cube data to real Windows input")
    print()
    
    try:
        asyncio.run(connect_to_wsl())
    except KeyboardInterrupt:
        print("\n👋 Bridge stopped by user")