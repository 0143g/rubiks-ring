# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repository contains two main components:

1. **gan-web-bluetooth** - A TypeScript library for interacting with GAN Smart Timers and Smart Cubes via Web Bluetooth API
2. **reverse.py** - A Python utility for reverse engineering GAN cube bluetooth protocols using the `bleak` library

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

### Python Script
```bash
python reverse.py       # Run bluetooth scanner/monitor for GAN cubes
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

### Python Reverse Engineering Tool

The `reverse.py` script provides bluetooth scanning and protocol analysis capabilities:
- Automatic GAN device discovery by name patterns
- Service and characteristic enumeration
- Raw bluetooth notification monitoring
- Hex dump analysis for protocol reverse engineering

## Development Notes

### Cube Clock Synchronization
GAN Smart Cubes have internal clocks that drift from host device time. The library includes `cubeTimestampLinearFit()` function that uses linear regression to align cube timestamps with host timestamps for accurate solve timing.

### Encryption Requirements
All GAN cube communications require AES encryption with device-specific salts derived from MAC addresses. The library automatically handles MAC retrieval via Web Bluetooth advertisement monitoring or custom providers.

### Supported Browsers
Limited to browsers with Web Bluetooth API support. See [implementation status](https://github.com/WebBluetoothCG/web-bluetooth/blob/main/implementation-status.md).