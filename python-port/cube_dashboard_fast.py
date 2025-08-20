#!/usr/bin/env python3
"""
Fast GAN Smart Cube Dashboard Server - Optimized for responsiveness
Disables high-frequency orientation updates to prioritize move detection.
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


class FastCubeDashboardServer:
    """Optimized web dashboard server for GAN Smart Cube - prioritizes move detection."""
    
    def __init__(self, enable_orientation=False):
        self.app = Flask(__name__, template_folder='templates', static_folder='static')
        self.app.config['SECRET_KEY'] = 'gan-cube-dashboard-secret'
        # Reduced buffer size for better performance
        self.socketio = SocketIO(
            self.app, 
            cors_allowed_origins="*", 
            async_mode='threading',
            engineio_logger=False,
            socketio_logger=False
        )
        
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
        
        # Performance optimization settings
        self.enable_orientation = enable_orientation
        self.last_orientation_emit = 0
        self.orientation_rate_limit = 500  # Very slow orientation updates (2 FPS)
        self.last_state_emit = 0
        self.state_rate_limit = 1000  # Max 1 state update per second
        
        print(f"🚀 Fast Dashboard Mode - Orientation: {'ON' if enable_orientation else 'OFF'}")
        
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
            self.emit_status_update()
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            print(f"🌐 Client disconnected: {request.sid}")
        
        @self.socketio.on('connect_cube')
        def handle_connect_cube(data=None):
            device_address = data.get('device_address') if data else None
            self.connect_to_cube(device_address)
        
        @self.socketio.on('disconnect_cube')
        def handle_disconnect_cube(data=None):
            self.disconnect_from_cube()
        
        @self.socketio.on('request_state')
        def handle_request_state(data=None):
            self.request_cube_state()
        
        @self.socketio.on('request_battery')
        def handle_request_battery(data=None):
            self.request_cube_battery()
        
        @self.socketio.on('clear_history')
        def handle_clear_history(data=None):
            self.move_history.clear()
            self.emit_move_history()
    
    def connect_to_cube(self, device_address: Optional[str] = None):
        """Connect to GAN Smart Cube."""
        if self.is_connected:
            self.socketio.emit('message', {'type': 'warning', 'text': 'Already connected to cube'})
            return
        
        self.connection_status = "connecting"
        self.emit_status_update()
        
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
            self.cube_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.cube_loop)
            
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
            self.cube = GanSmartCube()
            
            # Setup event handlers
            self.cube.on('move', self._handle_move_event)
            self.cube.on('facelets', self._handle_facelets_event)
            if self.enable_orientation:
                self.cube.on('orientation', self._handle_orientation_event)
            self.cube.on('battery', self._handle_battery_event)
            self.cube.on('hardware', self._handle_hardware_event)
            self.cube.on('connected', self._handle_connected_event)
            self.cube.on('disconnected', self._handle_disconnected_event)
            
            self.socketio.emit('message', {'type': 'info', 'text': 'Scanning for cube...'})
            await self.cube.connect(device_address)
            
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
        """Handle move event from cube - PRIORITY EVENT."""
        print(f"🎯 MOVE: {event.move} (Serial: {event.serial})")
        
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
        
        # Keep last 30 moves (reduced for performance)
        if len(self.move_history) > 30:
            self.move_history.pop(0)
        
        # IMMEDIATELY emit move events - highest priority
        try:
            self.socketio.emit('move', move_data)
            # Emit history less frequently
            if len(self.move_history) % 3 == 0:  # Every 3rd move
                self.emit_move_history()
        except Exception as e:
            print(f"❌ Error emitting move: {e}")
    
    def _handle_facelets_event(self, event: GanCubeFaceletsEvent):
        """Handle facelets event from cube with rate limiting."""
        current_time = now()
        
        # Rate limit state updates
        if current_time - self.last_state_emit < self.state_rate_limit:
            return
        
        self.current_state = {
            'facelets': event.facelets,
            'serial': event.serial,
            'timestamp': current_time,
            'cp': event.state.CP if event.state else None,
            'co': event.state.CO if event.state else None,
            'ep': event.state.EP if event.state else None,
            'eo': event.state.EO if event.state else None
        }
        
        self.socketio.emit('facelets', self.current_state)
        self.last_state_emit = current_time
    
    def _handle_orientation_event(self, event: GanCubeOrientationEvent):
        """Handle orientation event with heavy rate limiting."""
        if not self.enable_orientation:
            return
            
        current_time = now()
        
        # Heavy rate limiting for orientation
        if current_time - self.last_orientation_emit < self.orientation_rate_limit:
            return
        
        self.current_orientation = {
            'quaternion': {
                'x': round(event.quaternion.x, 3),  # Reduce precision
                'y': round(event.quaternion.y, 3),
                'z': round(event.quaternion.z, 3),
                'w': round(event.quaternion.w, 3)
            },
            'timestamp': current_time
        }
        
        self.socketio.emit('orientation', self.current_orientation)
        self.last_orientation_emit = current_time
    
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
            await asyncio.sleep(0.5)
            await self.cube.request_hardware_info()
            await asyncio.sleep(0.3)
            await self.cube.request_battery()
            await asyncio.sleep(0.3)
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
            'moves': self.move_history[-15:],  # Last 15 moves only
            'total_count': len(self.move_history)
        })
    
    def run(self, host='localhost', port=5000, debug=False):
        """Run the dashboard server."""
        print(f"🌐 Starting Fast GAN Cube Dashboard at http://{host}:{port}")
        print(f"⚡ Optimized for move detection responsiveness")
        self.socketio.run(self.app, host=host, port=port, debug=debug)


if __name__ == "__main__":
    import os
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    
    # Fast mode - orientation disabled by default
    server = FastCubeDashboardServer(enable_orientation=False)
    server.run(host='0.0.0.0', port=5000, debug=False)