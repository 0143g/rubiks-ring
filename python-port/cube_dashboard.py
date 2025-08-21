#!/usr/bin/env python3
"""
GAN Smart Cube Dashboard Server
A Flask-based web dashboard for monitoring and controlling GAN Smart Cubes.
"""

import asyncio
import json
import os
import threading
import time
import websockets
from typing import Optional, Dict, Any
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import sys
from pathlib import Path

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
    
    def __init__(self, config_path="controller_config.json"):
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
        
        # Orientation processing state (like simple-bridge.html)
        self.orientation_state = {
            'reference_orientation': None,
            'current_quaternion': None,
            'last_quaternion': None
        }
        
        # Debug output rate limiting (for terminal only)
        
        # Controller bridge connection
        self.controller_bridge_ws = None
        self.bridge_connected = False
        self.enable_controller = False
        self.last_orientation_debug = 0
        self.orientation_debug_limit = 1000  # Print orientation to terminal once per second
        
        # Dashboard gets all data with minimal rate limiting
        self.last_orientation_emit = 0
        self.orientation_rate_limit = 16 # 60 FPS
        
        # Configuration management
        self.config_path = config_path
        self.config = {}
        self.config_mtime = 0.0
        self._load_config()
        
        self.setup_routes()
        self.setup_socketio_events()
    
    def _load_config(self):
        """Load configuration from JSON file"""
        try:
            config_file = Path(self.config_path)
            if config_file.exists():
                with open(config_file, 'r') as f:
                    self.config = json.load(f)
                    self.config_mtime = os.path.getmtime(self.config_path)
                    print(f"Loaded config from {self.config_path}")
            else:
                print(f"Config file {self.config_path} not found, using defaults")
                self.config = {}
        except Exception as e:
            print(f"Error loading config: {e}")
            self.config = {}
    
    def _check_and_reload_config(self):
        """Check if config file has been modified and reload if necessary"""
        try:
            current_mtime = os.path.getmtime(self.config_path)
            if current_mtime > self.config_mtime:
                print(f"\n🔄 Dashboard config file changed, reloading...")
                self._load_config()
                print("✅ Dashboard config reloaded")
        except (OSError, FileNotFoundError):
            pass  # Config file may not exist
        except Exception as e:
            print(f"Error checking config: {e}")
    
    def setup_routes(self):
        """Setup Flask routes."""
        
        @self.app.route('/')
        def index():
            return render_template('dashboard.html')
    
    def setup_socketio_events(self):
        """Setup WebSocket event handlers."""
        
        @self.socketio.on('connect')
        def handle_connect():
            print(f"Client connected: {request.sid}")
            # Send current state to new client
            self.emit_status_update()
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            print(f"Client disconnected: {request.sid}")
        
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
            print(f"Controller {'enabled' if enable else 'disabled'}")
            
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
        
        @self.socketio.on('reset_orientation')
        def handle_reset_orientation(data=None):
            """Reset controller orientation reference."""
            self.reset_controller_orientation()
        
        @self.socketio.on('calibrate_cube')
        def handle_calibrate_cube(data=None):
            """Calibrate cube with green face forward."""
            self.calibrate_cube()
    
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
            print(f"Cube connection error: {e}")
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
            print(f"Cube monitoring error: {e}")
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
                print(f"Disconnection error: {e}")
    
    def _handle_move_event(self, event: GanCubeMoveEvent):
        """Handle move event from cube."""
        print(f"Move: {event.move} (Serial: {event.serial})")
        
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
            print(f"Error emitting move event: {e}")
    
    def _handle_facelets_event(self, event: GanCubeFaceletsEvent):
        """Handle facelets event from cube."""
        print(f"State update: Serial {event.serial}")
        
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
            print(f"Error emitting facelets: {e}")
    
    def _handle_orientation_event(self, event: GanCubeOrientationEvent):
        """Handle orientation event from cube - fast dashboard updates with limited debug output."""
        current_time = now()
        
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
        
        # Store the raw quaternion directly without transformation for now
        raw_quat = {
            'x': event.quaternion.x,
            'y': event.quaternion.y,
            'z': event.quaternion.z,
            'w': event.quaternion.w
        }
        
        # Always store the last raw quaternion for calibration
        self._last_raw_quaternion = raw_quat.copy()
        
        # Calculate calibrated quaternion
        if hasattr(self, 'calibration_reference'):
            # Calculate the relative rotation from calibration reference to current
            ref = self.calibration_reference
            
            # Normalize reference quaternion
            ref_norm = (ref['x']**2 + ref['y']**2 + ref['z']**2 + ref['w']**2) ** 0.5
            ref_normalized = {
                'x': ref['x'] / ref_norm,
                'y': ref['y'] / ref_norm,
                'z': ref['z'] / ref_norm,
                'w': ref['w'] / ref_norm
            }
            
            # Calculate inverse (conjugate) of reference quaternion
            ref_inv = {
                'x': -ref_normalized['x'],
                'y': -ref_normalized['y'],
                'z': -ref_normalized['z'],
                'w': ref_normalized['w']
            }
            
            # Calculate relative rotation: relative = inverse(reference) * current
            # This gives us the rotation FROM reference TO current
            calibrated_quat = {
                'x': ref_inv['w']*raw_quat['x'] + ref_inv['x']*raw_quat['w'] + ref_inv['y']*raw_quat['z'] - ref_inv['z']*raw_quat['y'],
                'y': ref_inv['w']*raw_quat['y'] - ref_inv['x']*raw_quat['z'] + ref_inv['y']*raw_quat['w'] + ref_inv['z']*raw_quat['x'],
                'z': ref_inv['w']*raw_quat['z'] + ref_inv['x']*raw_quat['y'] - ref_inv['y']*raw_quat['x'] + ref_inv['z']*raw_quat['w'],
                'w': ref_inv['w']*raw_quat['w'] - ref_inv['x']*raw_quat['x'] - ref_inv['y']*raw_quat['y'] - ref_inv['z']*raw_quat['z']
            }
            
            # When the cube is at the calibration position, calibrated_quat should be (0,0,0,1) (identity)
            transformed_quat = calibrated_quat
        else:
            # No calibration - just use raw
            transformed_quat = raw_quat
            calibrated_quat = None
        
        # Store current quaternion for other uses
        self.orientation_state['current_quaternion'] = transformed_quat.copy()
        
        # Debug output to terminal (rate limited to once per second) - AFTER calibration
        if current_time - self.last_orientation_debug >= self.orientation_debug_limit:
            if calibrated_quat is not None:
                # Show calibrated values
                q = calibrated_quat
                print(f"Orientation (calibrated): x={q['x']:.3f}, y={q['y']:.3f}, z={q['z']:.3f}, w={q['w']:.3f}")
            else:
                # Show raw values with warning
                q = event.quaternion
                print(f"Orientation (RAW - not calibrated): x={q.x:.3f}, y={q.y:.3f}, z={q.z:.3f}, w={q.w:.3f}")
            self.last_orientation_debug = current_time
        
        # Emit to dashboard with high frequency for responsiveness
        try:
            # Add calibrated quaternion to the orientation data
            orientation_with_calibrated = self.current_orientation.copy()
            if calibrated_quat is not None:
                orientation_with_calibrated['calibrated_quaternion'] = calibrated_quat
                orientation_with_calibrated['is_calibrated'] = True
            else:
                orientation_with_calibrated['is_calibrated'] = False
            
            self.socketio.emit('orientation', orientation_with_calibrated)
            self.last_orientation_emit = current_time
            
            # Forward to controller bridge if enabled and connected
            if self.enable_controller and self.bridge_connected:
                # Use calibrated quaternion if available, otherwise raw
                quat_for_controller = calibrated_quat if calibrated_quat is not None else raw_quat
                
                # Create a quaternion object for the controller processing
                from gan_web_bluetooth.utils import Quaternion
                controller_quat = Quaternion(
                    x=quat_for_controller['x'],
                    y=quat_for_controller['y'], 
                    z=quat_for_controller['z'],
                    w=quat_for_controller['w']
                )
                
                # Process orientation using calibrated quaternion
                controller_data = self._process_orientation_for_controller(controller_quat, current_time)
                if controller_data:
                    self._forward_to_controller_bridge('CUBE_ORIENTATION', controller_data)
                    
                    # Handle automatic B button press/release
                    auto_b_button = controller_data.get('auto_b_button', False)
                    if auto_b_button != getattr(self, '_last_auto_b_state', False):
                        if auto_b_button:
                            # Send B button press
                            b_move_data = {
                                'move': 'AUTO_B_PRESS',
                                'face': 'AUTO',
                                'direction': 'PRESS',
                                'timestamp': current_time,
                                'auto_generated': True
                            }
                            self._forward_to_controller_bridge('CUBE_MOVE', b_move_data)
                        else:
                            # Send B button release  
                            b_move_data = {
                                'move': 'AUTO_B_RELEASE',
                                'face': 'AUTO', 
                                'direction': 'RELEASE',
                                'timestamp': current_time,
                                'auto_generated': True
                            }
                            self._forward_to_controller_bridge('CUBE_MOVE', b_move_data)
                        
                        self._last_auto_b_state = auto_b_button
                
        except Exception as e:
            # Only print errors occasionally to avoid spam
            if current_time - getattr(self, 'last_emit_error', 0) > 5000:
                print(f"Error emitting orientation: {e}")
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
        
        # Auto-calibrate after a short delay to get initial orientation data
        if self.cube_loop:
            asyncio.run_coroutine_threadsafe(
                self._auto_calibrate_on_connect(),
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
            print(f"Error requesting initial info: {e}")
    
    async def _auto_calibrate_on_connect(self):
        """Automatically calibrate the cube after connection."""
        try:
            # Wait for orientation data to start flowing
            await asyncio.sleep(2.0)
            
            # Check if we have orientation data
            if hasattr(self, '_last_raw_quaternion'):
                print("\n🔄 Auto-calibrating cube...")
                self.socketio.emit('message', {
                    'type': 'info',
                    'text': '🔄 Auto-calibrating cube to current position...'
                })
                
                # Perform calibration
                self.calibrate_cube()
                
                print("📍 Place cube with GREEN face forward for optimal control")
                self.socketio.emit('message', {
                    'type': 'info',
                    'text': '📍 Place cube with GREEN face forward for optimal control'
                })
            else:
                print("⚠️ No orientation data received yet, skipping auto-calibration")
        except Exception as e:
            print(f"Error during auto-calibration: {e}")
    
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
            print(f"Connecting to controller bridge at {uri}")
            self.controller_bridge_ws = await websockets.connect(uri)
            self.bridge_connected = True
            print("Connected to controller bridge")
            
            # Start background task to maintain connection
            asyncio.create_task(self._maintain_bridge_connection())
            
        except Exception as e:
            print(f"Could not connect to controller bridge: {e}")
            self.bridge_connected = False
    
    async def _maintain_bridge_connection(self):
        """Maintain WebSocket connection to controller bridge."""
        try:
            if self.controller_bridge_ws:
                await self.controller_bridge_ws.wait_closed()
        except Exception as e:
            print(f"Controller bridge connection lost: {e}")
        finally:
            self.bridge_connected = False
            self.controller_bridge_ws = None
            print("Disconnected from controller bridge")
    
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
    
    def _process_orientation_for_controller(self, quaternion, current_time):
        """Process orientation data for analog joystick control. 
        Quaternion is already calibrated when passed to this function."""
        import math
        
        # The quaternion passed here is already calibrated, so just use it directly
        transformed_quat = {
            'x': quaternion.x,
            'y': quaternion.y,
            'z': quaternion.z,
            'w': quaternion.w
        }
        
        # Store current quaternion (this may be redundant now but keeping for compatibility)
        self.orientation_state['current_quaternion'] = transformed_quat.copy()
        
        # The incoming quaternion is already calibrated, so use it directly
        # When green face is forward, transformed_quat should be approximately (0, 0, 1, 0)
        # Use the calibrated quaternion directly for tilt calculations
        relative = transformed_quat
        
        # Check for config updates
        self._check_and_reload_config()
        
        # Get sensitivity settings from config
        sensitivity = self.config.get('sensitivity', {})
        tilt_x_sens = sensitivity.get('tilt_x_sensitivity', 2.5)
        tilt_y_sens = sensitivity.get('tilt_y_sensitivity', 2.5)
        spin_z_sens = sensitivity.get('spin_z_sensitivity', 2.0)
        
        # Extract tilt from quaternion components directly
        # INVERTED: Forward tilt should move forward, left tilt should move left
        raw_tilt_y = -relative['x'] * tilt_y_sens * 2  # Forward/back: INVERTED
        raw_tilt_x = relative['y'] * tilt_x_sens * 2  # Left/right: INVERTED 
        raw_spin_z = -relative['z'] * spin_z_sens  # Spin around vertical axis: NOW INVERTED FOR CONTROLS
        
        # Isolate primary axis to prevent diagonal movement (lines 677-688)
        tilt_x = 0.0
        tilt_y = 0.0
        abs_x = abs(raw_tilt_x)
        abs_y = abs(raw_tilt_y)
        
        # Only use the dominant axis, ignore the weaker one to prevent diagonal drift
        if abs_x > abs_y and abs_x > 0.15:
            tilt_x = max(-1.0, min(1.0, raw_tilt_x))  # Forward/back only
        elif abs_y > abs_x and abs_y > 0.15:
            tilt_y = max(-1.0, min(1.0, raw_tilt_y))  # Left/right only
        # If both are weak or equal, send zero (neutral position)
        
        # Process spin axis for right stick (no axis isolation needed)
        spin_z = max(-1.0, min(1.0, raw_spin_z))
        
        # Apply deadzone from config
        deadzone_settings = self.config.get('deadzone', {})
        deadzone = deadzone_settings.get('general_deadzone', 0.1)
        spin_deadzone = deadzone_settings.get('spin_deadzone', 0.1)  # Use consistent default
        
        # Apply more aggressive filtering to prevent drift
        if abs(tilt_x) < deadzone:
            tilt_x = 0
        if abs(tilt_y) < deadzone:
            tilt_y = 0
        
        # More aggressive spin filtering to prevent perpetual spinning
        if abs(spin_z) < spin_deadzone * 1.5:  # Increase effective deadzone for spin
            spin_z = 0
        elif abs(raw_spin_z) < 0.05:  # Also check raw value for very small movements
            spin_z = 0
        
        # Check for maximum stick input to trigger B button (sprint/run modifier)
        max_stick_threshold = 0.95  # 95% of max stick range triggers B button
        auto_b_button = False
        
        # If either forward/back (tilt_y) OR left/right (tilt_x) is near maximum, auto-press B button
        if abs(tilt_x) >= max_stick_threshold or abs(tilt_y) >= max_stick_threshold:
            auto_b_button = True
        
        # Debug output (rate limited)
        if hasattr(self, 'last_controller_debug') and current_time - self.last_controller_debug > 1000:
            if abs(tilt_x) > 0.1 or abs(tilt_y) > 0.1 or abs(spin_z) > 0.1:
                b_status = " + B BUTTON" if auto_b_button else ""
                print(f"Left Stick: X={tilt_x:.2f}, Y={tilt_y:.2f} | Right Stick: X={spin_z:.2f}{b_status}")
                self.last_controller_debug = current_time
        elif not hasattr(self, 'last_controller_debug'):
            self.last_controller_debug = current_time
        
        return {
            'tiltX': tilt_x,
            'tiltY': tilt_y, 
            'spinZ': spin_z,
            'auto_b_button': auto_b_button,  # New field for automatic B button
            'timestamp': current_time
        }
    
    def calibrate_cube(self):
        """Calibrate the cube when it's in the known position (green face forward, white on top).
        This stores the current quaternion as the calibration reference.
        """
        # Get the raw quaternion directly from the event, not the transformed one
        if not hasattr(self, '_last_raw_quaternion'):
            print("ERROR: No cube data yet. Connect cube first and place it with green face forward")
            self.socketio.emit('message', {
                'type': 'error',
                'text': 'No cube data! Connect cube first'
            })
            return
        
        # Store the current RAW quaternion as our "green face forward" reference
        self.calibration_reference = self._last_raw_quaternion.copy()
        
        print(f"CALIBRATION: Storing reference quaternion = ({self.calibration_reference['x']:.3f}, {self.calibration_reference['y']:.3f}, {self.calibration_reference['z']:.3f}, {self.calibration_reference['w']:.3f})")
        print("✅ Cube calibrated! This position is now identity (0,0,0,1)")
        print("📍 Controls: Tilt forward/back to move, tilt left/right to strafe, rotate to look around")
        
        self.socketio.emit('message', {
            'type': 'success',
            'text': '✅ Cube calibrated! Position reset to identity (0,0,0,1)'
        })
    
    def reset_controller_orientation(self, use_green_face=True):
        """Reset the controller orientation reference
        Args:
            use_green_face: If True (default), always reset to green face forward.
                          If False, reset to current cube position.
        """
        if use_green_face:
            # Reset to ACTUAL green face forward as the cube reports it
            self.orientation_state['reference_orientation'] = {
                'x': 0.0,
                'y': 0.0,
                'z': 0.765,  # ACTUAL value when green is forward
                'w': 0.644   # ACTUAL value when green is forward
            }
            print("Controller orientation LOCKED to ACTUAL GREEN FACE FORWARD (0, 0, 0.765, 0.644)")
            self.socketio.emit('message', {
                'type': 'success',
                'text': 'Controller locked to GREEN FACE FORWARD - hold cube with green facing you'
            })
        elif self.orientation_state['current_quaternion']:
            # Optional: Reset reference to current position (not recommended)
            self.orientation_state['reference_orientation'] = self.orientation_state['current_quaternion'].copy()
            print("Controller orientation reset - current position is now neutral")
            
            self.socketio.emit('message', {
                'type': 'success', 
                'text': 'Controller orientation reset - current position is now neutral'
            })
        else:
            print("No orientation data yet - connect cube first")
            self.socketio.emit('message', {
                'type': 'warning',
                'text': 'No orientation data yet - connect cube first'
            })

    async def _send_to_bridge(self, message: Dict[str, Any]):
        """Send message to controller bridge WebSocket."""
        try:
            if self.controller_bridge_ws and not self.controller_bridge_ws.closed:
                await self.controller_bridge_ws.send(json.dumps(message))
        except Exception as e:
            if hasattr(self, 'last_bridge_error_time'):
                current_time = time.time() * 1000
                if current_time - self.last_bridge_error_time > 5000:  # Rate limit error messages
                    print(f"Error sending to controller bridge: {e}")
                    self.last_bridge_error_time = current_time
            else:
                print(f"Error sending to controller bridge: {e}")
                self.last_bridge_error_time = time.time() * 1000
    
    def run(self, host='localhost', port=5000, debug=False):
        """Run the dashboard server."""
        print(f"Starting GAN Cube Dashboard at http://{host}:{port}")
        self.socketio.run(self.app, host=host, port=port, debug=debug)


if __name__ == "__main__":
    # Create templates directory if it doesn't exist
    import os
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    
    server = CubeDashboardServer()
    server.run(host='0.0.0.0', port=5000, debug=False)
