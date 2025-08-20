#!/usr/bin/env python3
"""
GAN Smart Cube Dashboard Server
A Flask-based web dashboard for monitoring and controlling GAN Smart Cubes.
"""

import asyncio
import json
import threading
import time
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
        
        # Emit to clients
        self.socketio.emit('move', move_data)
        self.emit_move_history()
    
    def _handle_facelets_event(self, event: GanCubeFaceletsEvent):
        """Handle facelets event from cube."""
        self.current_state = {
            'facelets': event.facelets,
            'serial': event.serial,
            'timestamp': now(),
            'cp': event.state.CP if event.state else None,
            'co': event.state.CO if event.state else None,
            'ep': event.state.EP if event.state else None,
            'eo': event.state.EO if event.state else None
        }
        
        self.socketio.emit('facelets', self.current_state)
    
    def _handle_orientation_event(self, event: GanCubeOrientationEvent):
        """Handle orientation event from cube."""
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
            'timestamp': now()
        }
        
        self.socketio.emit('orientation', self.current_orientation)
    
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