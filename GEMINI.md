# GEMINI.md

This file provides guidance to Qwen Code when working with code in this repository.

## Project Overview

This repository is focused on creating a system to use a GAN Smart Cube as a controller for Elden Ring. The system consists of:

1. **gan-web-bluetooth** - A TypeScript library for interacting with GAN Smart Cubes via Web Bluetooth API
2. **wsl-cube-receiver.js** - A Node.js WebSocket server that receives cube events from a browser
3. **Elden Ring Controller** - A future Node.js application that will map cube rotations to keyboard inputs and gyro data to mouse movement for Elden Ring

The core goal is to transform a physical GAN Rubik's Cube (specifically a GAN356 i3 cube with MAC address AB:12:34:62:BC:15) into a gaming controller for Elden Ring with minimal latency.

## Architecture

### Current Architecture
```
GAN Cube (bluetooth) → Browser (Web Bluetooth) → WebSocket → Node.js Receiver → Elden Ring
                            ↑
                    gan-web-bluetooth lib
```

### Planned Architecture
```
GAN Cube (bluetooth) → Node.js App (Bluetooth) → Keyboard/Mouse Simulation → Elden Ring
                             ↑
                       gan-web-bluetooth lib
```

## Key Components

### gan-web-bluetooth Library

**Purpose**: TypeScript library for connecting to and communicating with GAN Smart Cubes via Web Bluetooth API

**Core Features**:
- Multi-protocol support (Gen2, Gen3, Gen4) for different GAN cube models
- AES encryption handling with MAC address-based key salting
- RxJS Observables for real-time cube events
- Gyroscope support for orientation tracking
- Cube state synchronization using linear regression to handle clock drift

**Key Files**:
- `src/gan-smart-cube.ts` - Main cube connection logic
- `src/gan-cube-encrypter.ts` - AES encryption implementation
- `src/gan-cube-definitions.ts` - Bluetooth service/characteristic UUIDs and encryption keys
- `src/gan-cube-protocol.ts` - Protocol drivers for different GAN generations
- `src/utils.ts` - Time utilities and cube state conversion functions

**Supported Cube Models**:
- GAN Gen2: GAN Mini ui FreePlay, GAN12 ui, GAN356 i series, Monster Go 3Ai, MoYu AI 2023
- GAN Gen3: GAN356 i Carry 2
- GAN Gen4: GAN12 ui Maglev, GAN14 ui FreePlay

### wsl-cube-receiver.js

**Purpose**: Node.js WebSocket server that receives cube events from a browser and displays them in the terminal

**Features**:
- WebSocket server on port 8080
- Color-coded terminal output for different event types
- Move counting and timing information
- Gyroscope quaternion display
- Graceful shutdown handling

### Browser Bridge (simple-bridge.html)

**Purpose**: HTML page that connects to the cube via Web Bluetooth and relays events via WebSocket to the Node.js receiver

**Features**:
- 3D cube visualization using Three.js
- Real-time gyroscope orientation display
- Cube information panel (battery, hardware, etc.)
- WebSocket connection to Node.js receiver
- Move history logging

## Build Commands

### gan-web-bluetooth Library
```bash
cd gan-web-bluetooth
npm install              # Install dependencies
npm run build           # Full build: clean, compile types, compile bundles
npm run clean           # Remove dist/ directory
npm run compile:types   # Compile TypeScript declarations
npm run compile:bundles # Build ES and CJS bundles with Rollup
```

### wsl-cube-receiver.js
```bash
node wsl-cube-receiver.js  # Run the WebSocket receiver
```

### Browser Bridge
Simply open `simple-bridge.html` in a browser that supports Web Bluetooth API

## Development Notes

### Encryption Mechanism
All GAN cube communications require AES encryption:
1. Base encryption key is retrieved from `GAN_ENCRYPTION_KEYS`
2. MAC address is extracted from Bluetooth manufacturer data
3. Salt is created by reversing the MAC address bytes
4. Key and IV are modified by adding salt values
5. AES-128-CBC encryption is used for all communications

### Cube Connection Flow
1. User selects cube via browser Bluetooth dialog
2. MAC address is retrieved via advertisement watching or manual entry
3. Encryption salt is derived from MAC address
4. GATT connection is established
5. Services are enumerated to determine cube generation
6. Appropriate encrypter and protocol driver are initialized
7. Connection object with event observable is returned

### Event System
The library uses RxJS Observables to emit events:
- MOVE events for cube rotations
- GYRO events for orientation changes
- FACELETS events for cube state
- BATTERY events for power level
- HARDWARE events for device information
- DISCONNECT events for connection loss

### Time Synchronization
GAN cubes have internal clocks that drift from host time. The library includes:
- `cubeTimestampLinearFit()` - Uses linear regression to align cube timestamps with host timestamps
- `cubeTimestampCalcSkew()` - Calculates clock drift percentage

## Project Goals

As documented in GOAL.md, the project aims to:

1. Create a Node.js application that connects to the GAN cube using the existing library
2. Map cube rotations to keyboard inputs for Elden Ring
3. Use gyro data for camera/mouse movement
4. Run outside browser for minimal latency
5. Achieve <50ms latency from cube movement to game input

## Challenges to Address

1. **Node.js Compatibility**: The library currently requires Web Bluetooth API. Need to investigate using node.js bluetooth adapters like @abandonware/noble
2. **Encryption/Connection Analysis**: Understanding how MAC→AES key derivation works and connection flow for Gen2 protocol
3. **Event System**: Documenting exact structure of move events and gyro/quaternion data formatting
4. **Control Mapping**: Determining optimal move notation to game action mapping and implementing smooth mouse movement from gyro quaternions
5. **Performance**: Ensuring <50ms latency for gaming responsiveness