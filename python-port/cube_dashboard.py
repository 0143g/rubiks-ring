#!/usr/bin/env python3
"""
GAN Smart Cube Dashboard Server
A Flask-based web dashboard for monitoring and controlling GAN Smart Cubes.
"""

import asyncio
import json
import threading
import time
import websockets
from typing import Optional, Dict, Any
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import sys

try:
    from gan_web_bluetooth import GanSmartCube
    from gan_web_bluetooth.protocols.base import (
        GanCubeMoveEvent, GanCubeFaceletsEvent, GanCubeOrientationEvent,
        GanCubeBatteryEvent, GanCubeHardwareEvent
    )
    from gan_web_bluetooth.utils import now
except ImportError as e:
    print(f"Error importing gan_web_bluetooth: {e}")
    sys.exit(1)


class CubeDashboardServer:
    """Web dashboard server for GAN Smart Cube."""
    
    def __init__(self):
        self.app = Flask(__name__, template_folder='templates', static_folder='static')
        self.app.config['SECRET_KEY'] = 'gan-cube-dashboard-secret'
        self.socketio = SocketIO(self.app, cors_allowed_origins="*", async_mode='threading')
        
        self.cube: Optional[GanSmartCube] = None
        self.cube_thread: Optional[threading.Thread] = None
        self.cube_loop: Optional[asyncio.AbstractEventLoop] = None
        self.is_connected = False
        self.connection_status = "disconnected"
        
        # Dashboard state
        self.move_history = []
        self.current_state = None
        self.current_orientation = None
        self.battery_level = None
        self.hardware_info = {}
        self.connection_info = {}
        
        # Debug output rate limiting (for terminal only)
        
        # Controller bridge connection
        self.controller_bridge_ws = None
        self.bridge_connected = False
        self.enable_controller = False
        self.last_orientation_debug = 0
        self.orientation_debug_limit = 1000  # Print orientation to terminal once per second
        
        # Dashboard gets all data with minimal rate limiting
        self.last_orientation_emit = 0
        self.orientation_rate_limit = 16  # 60 FPS for dashboard responsiveness
        
        self.setup_routes()
        self.setup_socketio_events()
    
    def setup_routes(self):
        """Setup Flask routes."""
        
        @self.app.route('/')
        def index():
            return render_template('dashboard.html')
    
    def setup_socketio_events(self):
        """Setup WebSocket event handlers."""
        
        @self.socketio.on('connect')
        def handle_connect():
            print(f"🌐 Client connected: {request.sid}")
            # Send current state to new client
            self.emit_status_update()
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            print(f"🌐 Client disconnected: {request.sid}")
        
        @self.socketio.on('connect_cube')
        def handle_connect_cube(data=None):
            """Handle cube connection request."""
            device_address = data.get('device_address') if data else None
            self.connect_to_cube(device_address)
        
        @self.socketio.on('disconnect_cube')
        def handle_disconnect_cube(data=None):
            """Handle cube disconnection request."""
            self.disconnect_from_cube()
        
        @self.socketio.on('request_state')
        def handle_request_state(data=None):
            """Handle state request."""
            self.request_cube_state()
        
        @self.socketio.on('request_battery')
        def handle_request_battery(data=None):
            """Handle battery request."""
            self.request_cube_battery()
        
        @self.socketio.on('clear_history')
        def handle_clear_history(data=None):
            """Clear move history."""
            self.move_history.clear()
            self.emit_move_history()
        
        @self.socketio.on('enable_controller')
        def handle_enable_controller(data=None):
            """Enable/disable controller bridge forwarding."""
            enable = data.get('enable', False) if data else False
            self.enable_controller = enable
            print(f"🎮 Controller {'enabled' if enable else 'disabled'}")
            
            # Try to connect to bridge if enabling
            if enable and not self.bridge_connected and self.cube_loop:
                asyncio.run_coroutine_threadsafe(
                    self.connect_to_controller_bridge(),
                    self.cube_loop
                )
        
        @self.socketio.on('connect_controller_bridge')
        def handle_connect_controller_bridge(data=None):
            """Connect to controller bridge server."""
            host = data.get('host', 'localhost') if data else 'localhost'
            port = data.get('port', 8083) if data else 8083
            
            if self.cube_loop:
                asyncio.run_coroutine_threadsafe(
                    self.connect_to_controller_bridge(host, port),
                    self.cube_loop
                )
    
    def connect_to_cube(self, device_address: Optional[str] = None):
        """Connect to GAN Smart Cube."""
        if self.is_connected:
            self.socketio.emit('message', {'type': 'warning', 'text': 'Already connected to cube'})
            return
        
        self.connection_status = "connecting"
        self.emit_status_update()
        
        # Start cube connection in separate thread
        self.cube_thread = threading.Thread(
            target=self._cube_connection_thread,
            args=(device_address,),
            daemon=True
        )
        self.cube_thread.start()
    
    def disconnect_from_cube(self):
        """Disconnect from cube."""
        if not self.is_connected:
            return
        
        self.connection_status = "disconnecting"
        self.emit_status_update()
        
        # Schedule disconnection in cube thread
        if self.cube_loop:
            asyncio.run_coroutine_threadsafe(
                self._disconnect_cube(),
                self.cube_loop
            )
    
    def request_cube_state(self):
        """Request current cube state."""
        if not self.is_connected or not self.cube:
            return
        
        if self.cube_loop:
            asyncio.run_coroutine_threadsafe(
                self.cube.get_state(),
                self.cube_loop
            )
    
    def request_cube_battery(self):
        """Request battery level."""
        if not self.is_connected or not self.cube:
            return
        
        if self.cube_loop:
            asyncio.run_coroutine_threadsafe(
                self.cube.request_battery(),
                self.cube_loop
            )
    
    def _cube_connection_thread(self, device_address: Optional[str]):
        """Run cube connection in separate thread with its own event loop."""
        try:
            # Create new event loop for this thread
            self.cube_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.cube_loop)
            
            # Run the async cube connection
            self.cube_loop.run_until_complete(
                self._connect_and_monitor_cube(device_address)
            )
            
        except Exception as e:
            print(f"❌ Cube connection error: {e}")
            self.connection_status = "error"
            self.socketio.emit('message', {
                'type': 'error',
                'text': f'Connection failed: {str(e)}'
            })
            self.emit_status_update()
        finally:
            self.cube_loop = None
    
    async def _connect_and_monitor_cube(self, device_address: Optional[str]):
        """Connect to cube and monitor events."""
        try:
            # Create cube instance
            self.cube = GanSmartCube()
            
            # Setup event handlers
            self.cube.on('move', self._handle_move_event)
            self.cube.on('facelets', self._handle_facelets_event)
            self.cube.on('orientation', self._handle_orientation_event)
            self.cube.on('battery', self._handle_battery_event)
            self.cube.on('hardware', self._handle_hardware_event)
            self.cube.on('connected', self._handle_connected_event)
            self.cube.on('disconnected', self._handle_disconnected_event)
            
            # Connect to cube
            self.socketio.emit('message', {'type': 'info', 'text': 'Scanning for cube...'})
            await self.cube.connect(device_address)
            
            # Wait for disconnection
            while self.is_connected:
                await asyncio.sleep(0.1)
                
        except Exception as e:
            print(f"❌ Cube monitoring error: {e}")
            self.connection_status = "error"
            self.socketio.emit('message', {
                'type': 'error',
                'text': f'Connection error: {str(e)}'
            })
            self.emit_status_update()
    
    async def _disconnect_cube(self):
        """Disconnect from cube."""
        if self.cube:
            try:
                await self.cube.disconnect()
            except Exception as e:
                print(f"❌ Disconnection error: {e}")
    
    def _handle_move_event(self, event: GanCubeMoveEvent):
        """Handle move event from cube."""
        print(f"🎯 Move: {event.move} (Serial: {event.serial})")
        
        move_data = {
            'move': event.move,
            'face': event.face,
            'direction': event.direction,
            'serial': event.serial,
            'timestamp': now(),
            'cube_timestamp': event.cube_timestamp
        }
        
        # Add to history
        self.move_history.append(move_data)
        
        # Keep last 50 moves
        if len(self.move_history) > 50:
            self.move_history.pop(0)
        
        # Emit to dashboard immediately for maximum responsiveness
        try:
            self.socketio.emit('move', move_data)
            self.emit_move_history()
            
            # Forward to controller bridge if enabled and connected
            if self.enable_controller and self.bridge_connected:
                self._forward_to_controller_bridge('CUBE_MOVE', move_data)
                
        except Exception as e:
            print(f"❌ Error emitting move event: {e}")
    
    def _handle_facelets_event(self, event: GanCubeFaceletsEvent):
        """Handle facelets event from cube."""
        print(f"📋 State update: Serial {event.serial}")
        
        self.current_state = {
            'facelets': event.facelets,
            'serial': event.serial,
            'timestamp': now(),
            'cp': event.state.CP if event.state else None,
            'co': event.state.CO if event.state else None,
            'ep': event.state.EP if event.state else None,
            'eo': event.state.EO if event.state else None
        }
        
        # Emit immediately to dashboard for fast updates
        try:
            self.socketio.emit('facelets', self.current_state)
        except Exception as e:
            print(f"❌ Error emitting facelets: {e}")
    
    def _handle_orientation_event(self, event: GanCubeOrientationEvent):
        """Handle orientation event from cube - fast dashboard updates with limited debug output."""
        current_time = now()
        
        # Debug output to terminal (rate limited to once per second)
        if current_time - self.last_orientation_debug >= self.orientation_debug_limit:
            q = event.quaternion
            print(f"🌐 Orientation: x={q.x:.3f}, y={q.y:.3f}, z={q.z:.3f}, w={q.w:.3f}")
            self.last_orientation_debug = current_time
        
        # Light rate limiting for dashboard (60 FPS)
        if current_time - self.last_orientation_emit < self.orientation_rate_limit:
            return
        
        self.current_orientation = {
            'quaternion': {
                'x': event.quaternion.x,
                'y': event.quaternion.y,
                'z': event.quaternion.z,
                'w': event.quaternion.w
            },
            'angular_velocity': {
                'x': event.angular_velocity.x if event.angular_velocity else 0,
                'y': event.angular_velocity.y if event.angular_velocity else 0,
                'z': event.angular_velocity.z if event.angular_velocity else 0
            } if event.angular_velocity else None,
            'timestamp': current_time
        }
        
        # Emit to dashboard with high frequency for responsiveness
        try:
            self.socketio.emit('orientation', self.current_orientation)
            self.last_orientation_emit = current_time
            
            # Forward to controller bridge if enabled and connected
            if self.enable_controller and self.bridge_connected:
                # Convert quaternion to tilt values for controller
                from gan_web_bluetooth.utils import quaternion_to_euler, Quaternion
                
                # Apply the same axis transformation as working TypeScript implementation
                raw_quat = event.quaternion
                
                # Transform quaternion using same mapping as simple-bridge.html (line 630-636)
                transformed_quat = Quaternion(
                    x=-raw_quat.x,  # cube x → -x (matches working visualization)
                    y=raw_quat.z,   # cube z → y (up)
                    z=raw_quat.y,   # cube y → z (forward)
                    w=raw_quat.w
                )
                
                euler = quaternion_to_euler(transformed_quat)
                
                controller_data = {
                    'tiltX': euler[0] / 90.0,  # Normalize to -1 to 1 range
                    'tiltY': euler[1] / 90.0,
                    'spinZ': euler[2] / 180.0,
                    'timestamp': current_time
                }
                self._forward_to_controller_bridge('CUBE_ORIENTATION', controller_data)
                
        except Exception as e:
            # Only print errors occasionally to avoid spam
            if current_time - getattr(self, 'last_emit_error', 0) > 5000:
                print(f"❌ Error emitting orientation: {e}")
                self.last_emit_error = current_time
    
    def _handle_battery_event(self, event: GanCubeBatteryEvent):
        """Handle battery event from cube."""
        self.battery_level = {
            'percent': event.percent,
            'timestamp': now()
        }
        
        self.socketio.emit('battery', self.battery_level)
    
    def _handle_hardware_event(self, event: GanCubeHardwareEvent):
        """Handle hardware event from cube."""
        self.hardware_info = {
            'model': event.model,
            'firmware': event.firmware,
            'protocol': event.protocol,
            'timestamp': now()
        }
        
        self.socketio.emit('hardware', self.hardware_info)
    
    def _handle_connected_event(self, _):
        """Handle cube connected event."""
        self.is_connected = True
        self.connection_status = "connected"
        self.connection_info = {
            'connected_at': now(),
            'device_info': self.cube.device_info if self.cube else {}
        }
        
        self.socketio.emit('message', {'type': 'success', 'text': 'Connected to cube!'})
        self.emit_status_update()
        
        # Request initial information
        if self.cube_loop and self.cube:
            asyncio.run_coroutine_threadsafe(
                self._request_initial_info(),
                self.cube_loop
            )
    
    def _handle_disconnected_event(self, _):
        """Handle cube disconnected event."""
        self.is_connected = False
        self.connection_status = "disconnected"
        
        self.socketio.emit('message', {'type': 'info', 'text': 'Disconnected from cube'})
        self.emit_status_update()
    
    async def _request_initial_info(self):
        """Request initial cube information."""
        try:
            await asyncio.sleep(0.5)  # Give time for connection to stabilize
            await self.cube.request_hardware_info()
            await asyncio.sleep(0.2)
            await self.cube.request_battery()
            await asyncio.sleep(0.2)
            state = await self.cube.get_state()
        except Exception as e:
            print(f"❌ Error requesting initial info: {e}")
    
    def emit_status_update(self):
        """Emit status update to all clients."""
        status = {
            'connected': self.is_connected,
            'status': self.connection_status,
            'connection_info': self.connection_info,
            'hardware_info': self.hardware_info,
            'battery_level': self.battery_level
        }
        self.socketio.emit('status', status)
    
    def emit_move_history(self):
        """Emit move history to all clients."""
        self.socketio.emit('move_history', {
            'moves': self.move_history[-20:],  # Last 20 moves
            'total_count': len(self.move_history)
        })
    
    async def connect_to_controller_bridge(self, host='localhost', port=8083):
        """Connect to the controller bridge WebSocket server."""
        try:
            uri = f"ws://{host}:{port}"
            print(f"🎮 Connecting to controller bridge at {uri}")
            self.controller_bridge_ws = await websockets.connect(uri)
            self.bridge_connected = True
            print("✅ Connected to controller bridge")
            
            # Start background task to maintain connection
            asyncio.create_task(self._maintain_bridge_connection())
            
        except Exception as e:
            print(f"⚠️ Could not connect to controller bridge: {e}")
            self.bridge_connected = False
    
    async def _maintain_bridge_connection(self):
        """Maintain WebSocket connection to controller bridge."""
        try:
            if self.controller_bridge_ws:
                await self.controller_bridge_ws.wait_closed()
        except Exception as e:
            print(f"⚠️ Controller bridge connection lost: {e}")
        finally:
            self.bridge_connected = False
            self.controller_bridge_ws = None
            print("🔌 Disconnected from controller bridge")
    
    def _forward_to_controller_bridge(self, msg_type: str, data: Dict[str, Any]):
        """Forward message to controller bridge (non-blocking)."""
        if not self.bridge_connected or not self.controller_bridge_ws:
            return
        
        message = {
            'type': msg_type,
            **data
        }
        
        # Send message asynchronously without blocking
        if self.cube_loop:
            asyncio.run_coroutine_threadsafe(
                self._send_to_bridge(message),
                self.cube_loop
            )
    
    async def _send_to_bridge(self, message: Dict[str, Any]):
        """Send message to controller bridge WebSocket."""
        try:
            if self.controller_bridge_ws and not self.controller_bridge_ws.closed:
                await self.controller_bridge_ws.send(json.dumps(message))
        except Exception as e:
            if hasattr(self, 'last_bridge_error_time'):
                current_time = time.time() * 1000
                if current_time - self.last_bridge_error_time > 5000:  # Rate limit error messages
                    print(f"⚠️ Error sending to controller bridge: {e}")
                    self.last_bridge_error_time = current_time
            else:
                print(f"⚠️ Error sending to controller bridge: {e}")
                self.last_bridge_error_time = time.time() * 1000
    
    def run(self, host='localhost', port=5000, debug=False):
        """Run the dashboard server."""
        print(f"🌐 Starting GAN Cube Dashboard at http://{host}:{port}")
        self.socketio.run(self.app, host=host, port=port, debug=debug)


if __name__ == "__main__":
    # Create templates directory if it doesn't exist
    import os
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    
    server = CubeDashboardServer()
    server.run(host='0.0.0.0', port=5000, debug=False)
