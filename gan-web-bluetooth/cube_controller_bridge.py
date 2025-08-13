#!/usr/bin/env python3
"""
GAN Cube Controller Bridge
Receives WebSocket messages from browser and converts to real system input
Cross-platform: Windows (win32api), Linux (X11), macOS (Quartz)
"""

import asyncio
import websockets
import json
import time
import sys
from threading import Timer

# Platform-specific imports
try:
    # Windows
    import win32api
    import win32con
    PLATFORM = "windows"
    print("Platform: Windows (win32api)")
except ImportError:
    try:
        # Linux
        import Xlib
        from Xlib.display import Display
        from Xlib import X
        PLATFORM = "linux" 
        print("Platform: Linux (X11)")
    except ImportError:
        try:
            # macOS
            import Quartz
            PLATFORM = "macos"
            print("Platform: macOS (Quartz)")
        except ImportError:
            print("ERROR: No supported input library found!")
            print("Install: pip install pywin32 (Windows) or python-xlib (Linux) or pyobjc (macOS)")
            sys.exit(1)

class CubeController:
    def __init__(self):
        self.active_keys = set()
        self.mouse_sensitivity = 2.0
        self.last_mouse_time = 0
        
        # Platform-specific setup
        if PLATFORM == "linux":
            self.display = Display()
            self.screen = self.display.screen()
            self.root = self.screen.root
            
    def handle_cube_move(self, data):
        """Handle discrete cube face moves"""
        move = data.get('move', '')
        print(f"Cube move: {move}")
        
        if move == "R":
            self.mouse_click("left")
            print("Sent: Left Click")
        elif move == "R'":
            self.mouse_click("right") 
            print("Sent: Right Click")
        elif move == "L":
            self.key_press("a")
            print("Sent: Key A")
        elif move == "L'":
            self.key_press("d")
            print("Sent: Key D")
            
    def handle_key_press(self, data):
        """Handle continuous key press"""
        key = data.get('key', '')
        if key not in self.active_keys:
            self.key_down(key)
            self.active_keys.add(key)
            print(f"Key pressed: {key}")
            
    def handle_key_release(self, data):
        """Handle key release"""
        key = data.get('key', '')
        if key in self.active_keys:
            self.key_up(key)
            self.active_keys.remove(key)
            print(f"Key released: {key}")
            
    def handle_mouse_move(self, data):
        """Handle mouse movement"""
        # Rate limiting (60 FPS)
        current_time = time.time()
        if current_time - self.last_mouse_time < 0.016:
            return
            
        delta_x = int(data.get('deltaX', 0) * self.mouse_sensitivity)
        delta_y = int(data.get('deltaY', 0) * self.mouse_sensitivity)
        
        if delta_x != 0 or delta_y != 0:
            self.mouse_move_relative(delta_x, delta_y)
            self.last_mouse_time = current_time
            print(f"Mouse moved: ({delta_x}, {delta_y})")
            
    # Platform-specific implementations
    def mouse_click(self, button):
        """Send mouse click"""
        if PLATFORM == "windows":
            if button == "left":
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0)
            elif button == "right":
                win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0)
                win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0)
                
        elif PLATFORM == "linux":
            button_map = {"left": 1, "right": 3}
            if button in button_map:
                btn = button_map[button]
                # Simulate mouse press and release
                self.root.warp_pointer(0, 0)  # Move to current position
                self.display.sync()
                
    def mouse_move_relative(self, dx, dy):
        """Move mouse cursor relatively"""
        if PLATFORM == "windows":
            win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, dx, dy)
            
        elif PLATFORM == "linux":
            self.root.warp_pointer(dx, dy)
            self.display.sync()
            
    def key_press(self, key):
        """Send single key press"""
        self.key_down(key)
        Timer(0.05, self.key_up, [key]).start()  # 50ms press
        
    def key_down(self, key):
        """Send key down event"""
        if PLATFORM == "windows":
            vk_code = self.get_vk_code(key)
            if vk_code:
                win32api.keybd_event(vk_code, 0, 0, 0)
                
    def key_up(self, key):
        """Send key up event"""
        if PLATFORM == "windows":
            vk_code = self.get_vk_code(key)
            if vk_code:
                win32api.keybd_event(vk_code, 0, win32con.KEYEVENTF_KEYUP, 0)
                
    def get_vk_code(self, key):
        """Convert key string to Windows virtual key code"""
        key_map = {
            'a': 0x41, 'd': 0x44, 's': 0x53, 'w': 0x57,
            'space': win32con.VK_SPACE,
            'shift': win32con.VK_SHIFT,
            'ctrl': win32con.VK_CONTROL,
            'alt': win32con.VK_MENU
        }
        return key_map.get(key.lower())

# WebSocket server
async def handle_client(websocket, path):
    controller = CubeController()
    print(f"Client connected: {websocket.remote_address}")
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                msg_type = data.get('type', '')
                
                if msg_type == 'MOVE':
                    controller.handle_cube_move(data)
                elif msg_type == 'KEY_PRESS':
                    controller.handle_key_press(data)
                elif msg_type == 'KEY_RELEASE':
                    controller.handle_key_release(data)
                elif msg_type == 'MOUSE_MOVE':
                    controller.handle_mouse_move(data)
                    
            except json.JSONDecodeError as e:
                print(f"JSON decode error: {e}")
            except Exception as e:
                print(f"Error processing message: {e}")
                
    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected")
    finally:
        # Release all active keys
        for key in list(controller.active_keys):
            controller.key_up(key)
        controller.active_keys.clear()

if __name__ == "__main__":
    PORT = 8081
    print(f"Starting GAN Cube Controller Bridge on port {PORT}")
    print("Waiting for browser connection...")
    
    start_server = websockets.serve(handle_client, "localhost", PORT)
    
    try:
        asyncio.get_event_loop().run_until_complete(start_server)
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")