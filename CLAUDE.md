# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repository contains a comprehensive GAN Cube gaming controller system with multiple components:

### Core TypeScript Library
1. **gan-web-bluetooth/** - TypeScript library for GAN Smart Timers and Smart Cubes via Web Bluetooth API

### Gaming Controller Bridge System
2. **cube_controller_bridge.py** - Cross-platform WebSocket server for converting cube movements to gaming input (Windows/Linux/macOS)
3. **windows_input_server.py** - Windows-specific server with virtual Xbox gamepad support and enhanced input capabilities
4. **cube-controller.ahk** - High-performance AutoHotkey alternative for ultra-low latency Windows gaming
5. **simple-bridge.html** - Web dashboard for cube controller configuration, monitoring, and real-time cube state visualization

### Development & Debugging Tools
6. **wsl-cube-receiver.js** - Node.js WebSocket server for development, debugging, and monitoring cube events with colored terminal output

### Documentation & Configuration
7. **CONTROLLER_SETUP.md** - Comprehensive setup guide for gaming controller functionality
8. **ORIENTATION.txt** - Physical cube orientation reference for controller mapping
9. **TODO.txt** - Development tasks and project roadmap

## Build Commands

### TypeScript Library (gan-web-bluetooth)
```bash
cd gan-web-bluetooth
npm install              # Install dependencies
npm run build           # Full build: clean, compile types, compile bundles
npm run clean           # Remove dist/ directory
npm run compile:types   # Compile TypeScript declarations
npm run compile:bundles # Build ES and CJS bundles with Rollup
```

### Gaming Controller Bridge (Python)
```bash
# Cross-platform controller bridge
python cube_controller_bridge.py

# Windows-specific with virtual gamepad
python windows_input_server.py

# Development event monitor
node wsl-cube-receiver.js
```

### Gaming Controller Bridge (AutoHotkey - Windows)
```bash
# High-performance Windows alternative
# Requires: https://github.com/G33kDude/WebSocket.ahk
cube-controller.ahk
```

## Architecture

### TypeScript Library Structure

**Core Architecture:**
- **Event-driven design** using RxJS Observables for real-time cube/timer events
- **Multi-protocol support** with separate drivers for GAN Gen2, Gen3, and Gen4 protocols
- **Encryption layer** with protocol-specific encrypters using AES and device MAC addresses
- **Web Bluetooth API** integration for cross-platform browser compatibility

**Key Components:**

- `src/index.ts` - Main export module
- `src/gan-smart-timer.ts` - Timer connection, state management, and time recording
- `src/gan-smart-cube.ts` - Cube connection with automatic protocol detection
- `src/gan-cube-protocol.ts` - Protocol drivers and command/event definitions
- `src/gan-cube-encrypter.ts` - AES encryption for different GAN generations
- `src/gan-cube-definitions.ts` - Bluetooth UUIDs, encryption keys, and device constants
- `src/utils.ts` - Timestamp utilities, linear regression for cube clock sync, and Kociemba facelet conversion

**Protocol Support:**
- **GAN Gen2**: GAN Mini ui FreePlay, GAN12 ui, GAN356 i series, Monster Go 3Ai, MoYu AI 2023
- **GAN Gen3**: GAN356 i Carry 2  
- **GAN Gen4**: GAN12 ui Maglev, GAN14 ui FreePlay

**Key Design Patterns:**
- MAC address extraction from Bluetooth manufacturer data for encryption salt
- Linear regression algorithm for cube timestamp synchronization (addresses internal clock skew)
- Observable streams for move events, battery status, and cube state changes
- Protocol-agnostic command interface with automatic device detection

### Build System

- **TypeScript compilation** with strict settings and DOM/ES2020 targets
- **Dual output formats**: ES modules (`.mjs`) and CommonJS (`.cjs`) 
- **Rollup bundling** with external dependency handling
- **Type declarations** generated separately for library consumers

### Gaming Controller Architecture

**Controller Bridge System:**
- **WebSocket-based communication** between browser (Web Bluetooth) and system input injection
- **Multi-platform support** with platform-specific input libraries (win32api, X11, Quartz)
- **Virtual gamepad emulation** for enhanced game compatibility (Xbox controller simulation)
- **Real-time input processing** with configurable sensitivity, deadzone, and rate limiting
- **Orientation-based controls** converting cube tilt/rotation to analog stick movement and camera control

**Input Mapping:**
- **Discrete cube moves** (R, L, U, D, F, B) → Gaming actions (clicks, keys, gamepad buttons)
- **Continuous orientation** → Analog movement (WASD, mouse look, gamepad sticks)
- **Configurable mappings** for different game genres (FPS, racing, flight simulation)

**Performance Optimizations:**
- **Sub-10ms latency** target for competitive gaming
- **Rate limiting** and smoothing for stable input
- **Multiple bridge implementations** for different performance/compatibility needs

**Web Dashboard Features:**
- **Real-time cube visualization** with 3D rendering
- **Live orientation display** showing tilt, rotation, and angular velocity
- **Connection status monitoring** for cube, bridge, and WebSocket connections
- **Configuration interface** for sensitivity, deadzone, and control mappings

## Development Notes

### Cube Clock Synchronization
GAN Smart Cubes have internal clocks that drift from host device time. The library includes `cubeTimestampLinearFit()` function that uses linear regression to align cube timestamps with host timestamps for accurate solve timing.

### Encryption Requirements
All GAN cube communications require AES encryption with device-specific salts derived from MAC addresses. The library automatically handles MAC retrieval via Web Bluetooth advertisement monitoring or custom providers.

### Supported Browsers
Limited to browsers with Web Bluetooth API support. See [implementation status](https://github.com/WebBluetoothCG/web-bluetooth/blob/main/implementation-status.md).

## Gaming Controller Setup

### Quick Start (Windows)
1. **Install Python dependencies:** `pip install websockets pywin32 vgamepad`
2. **Start bridge server:** `python windows_input_server.py` (or `python cube_controller_bridge.py`)  
3. **Open dashboard:** Launch `simple-bridge.html` in Chrome/Edge
4. **Connect cube:** Click "Connect Cube" and select GAN device
5. **Start gaming:** Cube moves now control games as Xbox controller or keyboard/mouse

### Gaming Control Scheme
- **R/R' moves** → Attack/ADS (Right bumper/trigger)
- **L/L' moves** → Actions (B button or strafe keys)
- **Cube tilt** → Movement (WASD keys or left analog stick)
- **Cube rotation** → Camera (Mouse look or right analog stick)
- **Face moves U/D/F/B** → Additional game actions (configurable)

### Supported Game Types
- **FPS Games** (CS2, Valorant, Elden Ring) - Full movement and combat control
- **Racing Games** - Steering via cube tilt, face moves for gear shifts  
- **Flight Simulators** - 6DOF control via orientation, face moves for controls
- **Any game accepting keyboard/mouse or Xbox controller input**

## Current Project State

### Files Needed
**Essential Core Files:**
- `gan-web-bluetooth/src/` - Core TypeScript library (ALL files needed)
- `gan-web-bluetooth/package.json` - Library dependencies and build scripts
- `gan-web-bluetooth/rollup.config.js` - Build configuration
- `gan-web-bluetooth/tsconfig.json` - TypeScript compilation settings

**Gaming Controller System:**
- `simple-bridge.html` - Web dashboard (ESSENTIAL for user interface)
- `cube_controller_bridge.py` - Cross-platform bridge server
- `windows_input_server.py` - Windows-specific bridge with gamepad support
- `wsl-cube-receiver.js` - Development/debugging server
- `CONTROLLER_SETUP.md` - User setup documentation
- `ORIENTATION.txt` - Cube orientation reference

**Optional Enhancement Files:**
- `cube-controller.ahk` - High-performance Windows alternative
- `TODO.txt` - Development roadmap
- Root `package.json` - WebSocket dependency for wsl-cube-receiver.js

### Files Not Needed
- **NO reverse.py** - This file was mentioned in old documentation but does not exist
- **dist/ directories** - Generated build outputs (can be rebuilt)
- **node_modules/** - Package dependencies (reinstallable)

### Development Priorities
1. **Gaming controller latency optimization** - Target sub-10ms cube-to-game response
2. **Enhanced game compatibility** - Support for more input methods and games  
3. **Cross-platform bridge reliability** - Stable connections across Windows/Linux/macOS
4. **Dashboard UI improvements** - Better visualization and configuration options