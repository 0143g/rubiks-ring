# GAN Smart Cube Python Protocol Guide

This comprehensive guide explains how to work with GAN Smart Cubes using the Python implementation ported from the TypeScript gan-web-bluetooth library.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Protocol Details](#protocol-details)
- [Data Stream Parsing](#data-stream-parsing)
- [Event Types](#event-types)
- [Encryption](#encryption)
- [Code Examples](#code-examples)
- [Debugging](#debugging)

## Overview

GAN Smart Cubes communicate via Bluetooth Low Energy (BLE) using proprietary protocols. This library supports:

- **Gen2 Protocol**: GAN356 i series, GAN12 ui, Monster Go 3Ai, MoYu AI 2023
- **Gen3 Protocol**: GAN356 i Carry 2 (basic support)
- **Gen4 Protocol**: GAN12 ui Maglev, GAN14 ui FreePlay (basic support)

The primary focus is **Gen2 protocol** which is fully implemented and tested.

## Architecture

### Core Components

```
gan_web_bluetooth/
├── smart_cube.py          # Main cube interface
├── smart_timer.py         # Timer interface
├── definitions.py         # Constants and MAC extraction
├── utils.py              # Quaternion math and utilities
├── event_emitter.py      # Event system
├── platform_utils.py    # Cross-platform helpers
├── protocols/
│   ├── base.py           # Protocol interfaces
│   └── gen2.py           # Gen2 implementation
└── encryption/
    └── encrypters.py     # AES encryption
```

### Data Flow

```
Cube → BLE → Raw Encrypted Data → Decrypt → Parse Bits → Events → Your Code
```

## Quick Start

### 1. Install Dependencies

```bash
pip install bleak cryptography numpy flask flask-socketio python-socketio
```

Or install all requirements:
```bash
pip install -r requirements.txt
```

### 2. Basic Usage

```python
import asyncio
from gan_web_bluetooth import GanSmartCube

async def main():
    cube = GanSmartCube()
    
    # Event handlers
    cube.on('move', lambda event: print(f"Move: {event.move}"))
    cube.on('facelets', lambda event: print(f"State: {event.facelets}"))
    
    # Connect and listen
    await cube.connect()
    await asyncio.sleep(60)  # Listen for 60 seconds
    await cube.disconnect()

asyncio.run(main())
```

### 3. Web Dashboard

```bash
python run_dashboard.py  # Launch web dashboard at http://localhost:5000
```

### 4. Move Tracking Only

```bash
python track_moves.py  # Clean move detection without noise
```

### 5. Full Debug Stream

```bash
python debug_cube_stream.py  # See all raw data
```

## Protocol Details

### Connection Process

1. **Scan** for devices with names starting with "GAN", "MG", or "AiCube"
2. **Extract MAC address** from manufacturer advertisement data
3. **Detect protocol** by checking available BLE services:
   - Gen2: `6e400001-b5a3-f393-e0a9-e50e24dc4179`
   - Gen3: `8653000a-43e6-47b7-9cb0-5fc21d4ae340`
   - Gen4: `00000010-0000-fff7-fff6-fff5fff4fff0`
4. **Setup encryption** using MAC-derived salt
5. **Subscribe** to state characteristic notifications

### MAC Address Extraction

```python
def extract_mac_from_manufacturer_data(manufacturer_data: Dict[int, bytes]) -> str:
    # Check all Company Identifier Codes (0x0101, 0x0201, ..., 0xFF01)
    for cic in GAN_CIC_LIST:
        if cic in manufacturer_data:
            data = manufacturer_data[cic]
            if len(data) >= 6:
                # MAC is in last 6 bytes, reversed
                mac_bytes = list(data[:9])[-6:]
                mac_bytes.reverse()
                return ":".join(f"{byte:02X}" for byte in mac_bytes)
    return ""
```

## Data Stream Parsing

### Bit-Level Message Parsing

GAN cubes send data in bit-packed messages. The `ProtocolMessageView` class handles extraction:

```python
class ProtocolMessageView:
    def __init__(self, data: bytes):
        # Convert bytes to bit string: [0xFF, 0x00] → "1111111100000000"
        self.bits = ''.join(f'{byte:08b}' for byte in data)
    
    def get_bit_word(self, bit_offset: int, bit_length: int) -> int:
        # Extract specific bits and convert to integer
        bit_slice = self.bits[bit_offset:bit_offset + bit_length]
        return int(bit_slice, 2) if bit_slice else 0
```

### Event Type Detection

Events are identified by the first 4 bits of decrypted data:

```python
def decode_event(self, data: bytes) -> List[Event]:
    decrypted = self._decrypt(data)
    msg = ProtocolMessageView(decrypted)
    event_type = msg.get_bit_word(0, 4)  # First 4 bits
    
    if event_type == 0x01:     # Gyroscope/Orientation
        return self._handle_gyro_event(msg)
    elif event_type == 0x02:   # Move
        return self._handle_move_event(msg)
    elif event_type in [0x03, 0x04]:  # Facelets (varies by cube)
        return self._handle_facelets_event(msg)
    # ... etc
```

## Event Types

### 1. Move Events (0x02)

Triggered when cube faces are turned.

**Data Structure:**
- Bits 4-11: Serial number (0-255, circular)
- Bits 12-16: Face index for move 0 (0=U, 1=R, 2=F, 3=D, 4=L, 5=B)
- Bit 16: Direction for move 0 (0=CW, 1=CCW)
- Bits 47-62: Elapsed time since last move (cube timestamp)
- Additional moves packed in sequence

**Parsing:**
```python
def _handle_move_event(self, msg: ProtocolMessageView) -> List[GanCubeMoveEvent]:
    serial = msg.get_bit_word(4, 8)
    
    # Can contain up to 7 moves in buffer
    for i in range(7):
        face = msg.get_bit_word(12 + 5 * i, 4)
        direction = msg.get_bit_word(16 + 5 * i, 1)
        move_notation = "URFDLB"[face] + ("'" if direction else "")
```

### 2. Facelets Events (0x03/0x04)

Complete cube state in Corner/Edge Permutation/Orientation format.

**Data Structure:**
- Bits 4-11: Serial number
- Bits 12-32: Corner permutations (7 corners × 3 bits)
- Bits 33-46: Corner orientations (7 corners × 2 bits)
- Bits 47-90: Edge permutations (11 edges × 4 bits)
- Bits 91-101: Edge orientations (11 edges × 1 bit)

**8th corner/edge calculated from parity:**
```python
cp.append((28 - sum(cp)) % 8)      # 8th corner
co.append((3 - (sum(co) % 3)) % 3) # 8th corner orientation
ep.append((66 - sum(ep)) % 12)     # 12th edge
eo.append((2 - (sum(eo) % 2)) % 2) # 12th edge orientation
```

### 3. Gyroscope Events (0x01)

Real-time orientation data as quaternions.

**Data Structure:**
- Bits 4-19: Quaternion W component (signed 16-bit)
- Bits 20-35: Quaternion X component (signed 16-bit)
- Bits 36-51: Quaternion Y component (signed 16-bit)
- Bits 52-67: Quaternion Z component (signed 16-bit)

**Quaternion Conversion:**
```python
def _handle_gyro_event(self, msg: ProtocolMessageView) -> List[GanCubeOrientationEvent]:
    qw = msg.get_bit_word(4, 16)
    qx = msg.get_bit_word(20, 16)
    qy = msg.get_bit_word(36, 16)
    qz = msg.get_bit_word(52, 16)
    
    # Convert from 16-bit signed to normalized float
    quaternion = Quaternion(
        x=(1 - (qx >> 15) * 2) * (qx & 0x7FFF) / 0x7FFF,
        y=(1 - (qy >> 15) * 2) * (qy & 0x7FFF) / 0x7FFF,
        z=(1 - (qz >> 15) * 2) * (qz & 0x7FFF) / 0x7FFF,
        w=(1 - (qw >> 15) * 2) * (qw & 0x7FFF) / 0x7FFF
    )
```

### 4. Battery Events (0x09)

Battery level percentage.

**Data Structure:**
- Bits 8-15: Battery level (0-100)

### 5. Hardware Events (0x05)

Device information and capabilities.

**Data Structure:**
- Bits 8-15: Hardware major version
- Bits 16-23: Hardware minor version
- Bits 24-31: Software major version
- Bits 32-39: Software minor version
- Bits 40-103: Device name (8 ASCII characters)
- Bit 104: Gyroscope support flag

## Encryption

### AES-128-CBC Encryption

GAN cubes use AES encryption with MAC-address-based salting:

```python
class GanGen2CubeEncrypter:
    def __init__(self, key: bytes, iv: bytes, salt: bytes):
        # Apply salt to first 6 bytes of key and IV
        self._key = bytearray(key)
        self._iv = bytearray(iv)
        for i in range(6):
            self._key[i] = (key[i] + salt[i]) % 0xFF
            self._iv[i] = (iv[i] + salt[i]) % 0xFF
    
    def encrypt(self, data: bytes) -> bytes:
        # Encrypt first 16 bytes, then last 16 bytes (if length > 16)
        result = bytearray(data)
        self._encrypt_chunk(result, 0)
        if len(result) > 16:
            self._encrypt_chunk(result, len(result) - 16)
        return bytes(result)
```

### Encryption Keys

```python
GAN_ENCRYPTION_KEYS = [
    {   # Standard GAN key (Gen2/Gen3/Gen4)
        "key": [0x01, 0x02, 0x42, 0x28, 0x31, 0x91, 0x16, 0x07, 
                0x20, 0x05, 0x18, 0x54, 0x42, 0x11, 0x12, 0x53],
        "iv":  [0x11, 0x03, 0x32, 0x28, 0x21, 0x01, 0x76, 0x27,
                0x20, 0x95, 0x78, 0x14, 0x32, 0x12, 0x02, 0x43]
    },
    {   # MoYu AI 2023 key
        "key": [0x05, 0x12, 0x02, 0x45, 0x02, 0x01, 0x29, 0x56,
                0x12, 0x78, 0x12, 0x76, 0x81, 0x01, 0x08, 0x03],
        "iv":  [0x01, 0x44, 0x28, 0x06, 0x86, 0x21, 0x22, 0x28,
                0x51, 0x05, 0x08, 0x31, 0x82, 0x02, 0x21, 0x06]
    }
]
```

## Code Examples

### Complete Event Handling

```python
import asyncio
from gan_web_bluetooth import GanSmartCube

async def cube_example():
    cube = GanSmartCube()
    
    # Move detection
    def on_move(event):
        print(f"🎯 Move: {event.move}")
        print(f"   Face: {event.face}, Direction: {event.direction}")
        print(f"   Serial: {event.serial}")
        if event.cube_timestamp:
            print(f"   Cube Time: {event.cube_timestamp}ms")
    
    # State changes
    def on_facelets(event):
        print(f"📋 Cube State (Serial {event.serial}):")
        print(f"   Kociemba: {event.facelets}")
        print(f"   Corners: {event.state.CP}")
        print(f"   Edges: {event.state.EP}")
    
    # Orientation tracking
    def on_orientation(event):
        q = event.quaternion
        print(f"🌐 Orientation: x={q.x:.3f}, y={q.y:.3f}, z={q.z:.3f}, w={q.w:.3f}")
        
        if event.angular_velocity:
            v = event.angular_velocity
            print(f"   Angular Velocity: x={v.x:.2f}, y={v.y:.2f}, z={v.z:.2f}")
    
    # Battery monitoring
    def on_battery(event):
        print(f"🔋 Battery: {event.percent}%")
    
    # Device info
    def on_hardware(event):
        print(f"🔧 Hardware: {event.model}")
        print(f"   Firmware: {event.firmware}")
        print(f"   Protocol: {event.protocol}")
    
    # Connection events
    cube.on('move', on_move)
    cube.on('facelets', on_facelets)
    cube.on('orientation', on_orientation)
    cube.on('battery', on_battery)
    cube.on('hardware', on_hardware)
    cube.on('connected', lambda _: print("✅ Connected!"))
    cube.on('disconnected', lambda _: print("❌ Disconnected!"))
    
    try:
        # Auto-connect to first found cube
        await cube.connect()
        
        # Request information
        await cube.request_hardware_info()
        await cube.request_battery()
        state = await cube.get_state()
        
        # Listen for events
        await asyncio.sleep(60)
        
    finally:
        await cube.disconnect()

# Run the example
asyncio.run(cube_example())
```

### Raw Data Stream Analysis

```python
async def analyze_raw_stream():
    # Use debug_cube_stream.py for detailed packet analysis
    # Shows: encrypted → decrypted → bit parsing → events
    
    # Custom notification handler for raw analysis:
    def handle_raw_data(sender, data: bytes):
        print(f"Raw: {data.hex()}")
        
        # Decrypt
        decrypted = protocol._decrypt(data)
        print(f"Decrypted: {decrypted.hex()}")
        
        # Parse event type
        event_type = decrypted[0] & 0x0F
        print(f"Event Type: 0x{event_type:X}")
        
        # Show bit representation
        bits = ''.join(f'{b:08b}' for b in decrypted)
        print(f"Bits: {bits}")
```

### Quaternion Processing

```python
from gan_web_bluetooth.utils import (
    normalize_quaternion, slerp_quaternions, 
    smooth_orientation_data, CubeOrientationTransform
)

# Smooth orientation data
transform = CubeOrientationTransform()
orientation_buffer = []

def process_orientation(raw_quaternion):
    # Add to smoothing buffer
    orientation_buffer.append({
        'quaternion': raw_quaternion,
        'timestamp': time.time() * 1000
    })
    
    # Keep last 5 samples
    if len(orientation_buffer) > 5:
        orientation_buffer.pop(0)
    
    # Apply smoothing
    smoothed = smooth_orientation_data(orientation_buffer, window_size=3)
    
    # Normalize to standard orientation (white top, green front)
    normalized = transform.normalize_orientation(smoothed)
    
    return normalized
```

## Web Dashboard

### Real-Time Cube Monitoring

The included web dashboard provides a modern interface for monitoring cube activity:

```bash
python run_dashboard.py
# Open http://localhost:5000 in your browser
```

#### Dashboard Features

- **🎯 Move History** - Real-time move detection with clean notation (R, U', F, etc.)
- **📋 Cube State** - Live facelets display in Kociemba format
- **🌐 Orientation** - Real-time quaternion values updated at 60 FPS  
- **🔋 Battery Monitor** - Visual battery level indicator
- **📊 Statistics** - Session tracking and connection info
- **🔌 Connection Controls** - Connect/disconnect and information requests

#### Dashboard Architecture

```
Browser ←→ WebSocket ←→ Flask Server ←→ Cube Library ←→ GAN Cube
```

**Key Benefits:**
- Real-time updates via WebSocket
- Responsive design (desktop + mobile)
- Optimized for minimal latency
- Multiple client support
- Clean, modern UI

#### Performance Optimizations

The dashboard is optimized for responsiveness:
- **Move events**: Zero latency - immediate updates
- **Orientation data**: 60 FPS with browser animation frames
- **Terminal output**: Rate-limited debug (moves immediate, orientation 1/sec)
- **Error handling**: Minimal spam with periodic error reporting

## Available Tools

### Dashboard and Monitoring

1. **`run_dashboard.py`** - Web dashboard launcher (http://localhost:5000)
2. **`cube_dashboard.py`** - Main dashboard server with real-time monitoring
3. **`track_moves.py`** - Terminal-based clean move tracking
4. **`debug_cube_stream.py`** - Full packet analysis and debugging

### Examples and Testing

5. **`examples/cube_example.py`** - Complete cube usage example
6. **`examples/timer_example.py`** - Timer usage example  
7. **`test_gen2_implementation.py`** - Unit tests for protocol implementation

## Debugging

### Common Issues

**MAC Address Extraction Fails:**
```python
# Fallback to device address
if not mac_address:
    mac_address = device_address
    print("Warning: Using device address as MAC fallback")
```

**Encryption Errors:**
```python
# Check salt generation
mac_bytes = [int(x, 16) for x in mac_address.split(':')]
salt = bytes(reversed(mac_bytes))  # Must be reversed!
```

**Event Parsing Issues:**
```python
# Some cubes use 0x03 instead of 0x04 for facelets
elif event_type in [0x03, 0x04]:  # Handle both
    events.extend(self._handle_facelets_event(msg, timestamp))
```

### Debug Tools

1. **Web Dashboard** - `python run_dashboard.py` - Real-time monitoring with web interface
2. **Move Tracker** - `python track_moves.py` - Terminal-based clean move detection  
3. **Raw Debug Stream** - `python debug_cube_stream.py` - Full packet analysis with encryption details
4. **Unit Tests** - `python test_gen2_implementation.py` - Protocol validation tests

### Logging Strategy

```python
import logging

# Enable detailed logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('gan_cube')

# Log all events
def log_event(event_type, data):
    logger.debug(f"Event {event_type}: {data.hex()}")
```

## Performance Considerations

### Dashboard Optimizations

The included dashboard implements several performance optimizations:

- **Move Events**: Zero latency - highest priority with immediate emission
- **Orientation Data**: 60 FPS to dashboard, rate-limited debug output (1/sec) 
- **WebSocket Efficiency**: Uses requestAnimationFrame for smooth browser updates
- **Event Prioritization**: Moves > State > Orientation > Battery in priority order
- **Error Handling**: Minimal terminal spam with periodic error reporting

### General Guidelines

- **Rate Limiting**: Gyro events fire at 60+ FPS - implement app-specific rate limiting
- **Buffer Management**: Maintain limited-size buffers for smoothing (default: 5 samples)
- **Event Filtering**: Filter unnecessary events based on your application needs
- **Async Handling**: Use async/await properly to avoid blocking the event loop
- **Memory Management**: Clear old move history periodically for long-running sessions

## Coordinate Systems

**GAN Cube Internal Axes:**
- X-axis: Points toward RED face
- Y-axis: Points toward WHITE face (top)
- Z-axis: Points toward GREEN face (front)

**Standard Orientation Reference:**
- Identity: White top, Green front
- Quaternion (0,0,0,1) represents this position

This guide provides everything needed to understand and work with GAN Smart Cube data streams in Python. The implementation is fully functional for Gen2 cubes and provides a solid foundation for extending to other protocols.