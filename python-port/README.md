# gan-web-bluetooth Python Port

Python implementation of the gan-web-bluetooth library for interacting with GAN Smart Timers and Smart Cubes via Bluetooth Low Energy.

## Features

- **GAN Smart Timer Support** - Full timer functionality with state tracking
- **GAN Smart Cube Support** - Gen2 (fully implemented), Gen3/Gen4 (basic support)
- **Real-time Web Dashboard** - Modern web interface for cube monitoring
- **Automatic Protocol Detection** - Seamless connection to different cube generations
- **AES Encryption** - Secure communication with MAC-based salting
- **Move Detection** - Real-time face turn tracking with clean notation (R, U', F, etc.)
- **Orientation Tracking** - Live quaternion data at 60 FPS
- **Cross-platform Support** - Windows, Linux, macOS via Python + Bleak
- **Multiple Interfaces** - Web dashboard, terminal tools, and Python API

## Installation

```bash
# Install dependencies
pip install bleak cryptography numpy flask flask-socketio python-socketio

# Or install all requirements
pip install -r requirements.txt
```

## Quick Start

### Web Dashboard (Recommended)

Launch the real-time web dashboard for cube monitoring:

```bash
python run_dashboard.py
# Open http://localhost:5000 in your browser
```

**Features:**
- 🎯 **Real-time move detection** with instant dashboard updates
- 📋 **Live cube state** in Kociemba format  
- 🌐 **Orientation tracking** with smooth 60 FPS quaternion updates
- 🔋 **Battery monitoring** with visual indicator
- 📊 **Session statistics** and move history
- 🔌 **Connection controls** for easy cube management

### Terminal Tools

```bash
# Clean move tracking (terminal-based)
python track_moves.py

# Raw debug stream with packet analysis  
python debug_cube_stream.py

# Protocol validation tests
python test_gen2_implementation.py
```

### Connecting to a GAN Smart Timer

```python
import asyncio
from gan_web_bluetooth import GanSmartTimer

async def timer_example():
    timer = GanSmartTimer()
    
    # Set up event handlers
    timer.on('time_update', lambda time: print(f"Time: {time}ms"))
    timer.on('state_change', lambda state: print(f"State: {state}"))
    
    # Connect to timer
    await timer.connect()
    
    # Wait for events
    await asyncio.sleep(60)
    
    # Disconnect
    await timer.disconnect()

asyncio.run(timer_example())
```

### Connecting to a GAN Smart Cube

```python
import asyncio
from gan_web_bluetooth import GanSmartCube

async def cube_example():
    cube = GanSmartCube()
    
    # Set up event handlers
    cube.on('move', lambda move: print(f"Move: {move}"))
    cube.on('orientation', lambda data: print(f"Orientation: {data}"))
    
    # Connect to cube (auto-detects protocol)
    await cube.connect()
    
    # Get cube state
    state = await cube.get_state()
    print(f"Cube state: {state}")
    
    # Wait for moves
    await asyncio.sleep(60)
    
    # Disconnect
    await cube.disconnect()

asyncio.run(cube_example())
```

## Supported Devices

### GAN Smart Timers
- GAN Smart Timer
- GAN Halo Smart Timer

### GAN Smart Cubes

#### Gen2 Protocol
- GAN Mini ui FreePlay
- GAN12 ui
- GAN356 i, i2, i Play, i Carry S
- Monster Go 3Ai
- MoYu AI 2023

#### Gen3 Protocol
- GAN356 i Carry 2

#### Gen4 Protocol
- GAN12 ui Maglev
- GAN14 ui FreePlay

## Available Tools

### Dashboard and Monitoring
- **`run_dashboard.py`** - Web dashboard launcher (http://localhost:5000)
- **`cube_dashboard.py`** - Main dashboard server with real-time monitoring
- **`track_moves.py`** - Terminal-based clean move tracking
- **`debug_cube_stream.py`** - Full packet analysis and debugging

### Examples and Testing  
- **`examples/cube_example.py`** - Complete cube usage example
- **`examples/timer_example.py`** - Timer usage example
- **`test_gen2_implementation.py`** - Unit tests for protocol implementation

### Documentation
- **`GAN_CUBE_PROTOCOL_GUIDE.md`** - Comprehensive protocol documentation
- **`DASHBOARD_README.md`** - Dashboard-specific documentation
- **`MIGRATION_GUIDE.md`** - TypeScript to Python porting guide

## Architecture

The library is structured as follows:

- **`gan_web_bluetooth/`** - Main package
  - `smart_timer.py` - GAN Smart Timer implementation
  - `smart_cube.py` - GAN Smart Cube implementation with protocol auto-detection
  - `protocols/` - Protocol implementations for different cube generations
    - `gen2.py` - Complete Gen2 protocol (primary focus)
    - `base.py` - Protocol interfaces and base classes  
  - `encryption/` - AES encryption with MAC-based salting
  - `definitions.py` - Constants, UUIDs, and MAC extraction utilities
  - `utils.py` - Quaternion math, Kociemba conversion, timestamp sync
  - `event_emitter.py` - Event system for real-time notifications

## Development

### Setting up development environment

```bash
# Clone the repository
git clone https://github.com/yourusername/gan-web-bluetooth-python.git
cd gan-web-bluetooth-python

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode with dev dependencies
pip install -e .[dev]
```

### Running tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=gan_web_bluetooth --cov-report=html

# Run specific test file
pytest tests/test_encryption.py
```

### Code formatting and linting

```bash
# Format code with black
black gan_web_bluetooth/

# Lint with ruff
ruff gan_web_bluetooth/

# Type checking with mypy
mypy gan_web_bluetooth/
```

## Migration from TypeScript

This is a Python port of the original [gan-web-bluetooth](https://github.com/afedotov/gan-web-bluetooth) TypeScript library. See [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) for details on the porting process and architectural differences.

## License

MIT License - See LICENSE file for details

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Acknowledgments

- Original TypeScript library by [Andy Fedotov](https://github.com/afedotov)
- Based on reverse engineering work by the cubing community
