# gan-web-bluetooth Python Port

Python implementation of the gan-web-bluetooth library for interacting with GAN Smart Timers and Smart Cubes via Bluetooth Low Energy.

## Features

- Support for GAN Smart Timers
- Support for GAN Smart Cubes (Gen2, Gen3, Gen4 protocols)
- Automatic protocol detection
- AES encryption for secure communication
- Real-time move tracking and orientation sensing
- Cross-platform support (Windows, Linux, macOS)

## Installation

```bash
pip install gan-web-bluetooth
```

Or install from source:

```bash
git clone https://github.com/yourusername/gan-web-bluetooth-python.git
cd gan-web-bluetooth-python
pip install -e .
```

## Quick Start

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

## Architecture

The library is structured as follows:

- `gan_web_bluetooth/` - Main package
  - `smart_timer.py` - GAN Smart Timer implementation
  - `smart_cube.py` - GAN Smart Cube implementation
  - `protocols/` - Protocol implementations for different cube generations
  - `encryption/` - AES encryption for secure communication
  - `definitions.py` - Constants, UUIDs, and device definitions
  - `utils.py` - Utility functions for timestamps, quaternions, etc.

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