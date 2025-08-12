# Windows Port - GAN Cube Relay

This folder contains a standalone version of the GAN Cube Relay that runs natively on Windows without needing to connect to WSL.

## Features

- Connects directly to GAN Smart Cubes via Web Bluetooth
- 3D cube visualization using Three.js
- Real-time gyroscope orientation display
- Move detection and logging
- Battery and hardware information display
- No WSL or external server dependencies

## Requirements

- A Chromium-based browser (Chrome, Edge, etc.) that supports Web Bluetooth API
- A GAN Smart Cube (tested with GAN356 i3)
- Bluetooth adapter on your computer

## Usage

1. Copy the entire `windows-port` folder to your Windows machine
2. Open `cube-relay.html` in a Chromium-based browser
3. Click "Connect Cube" and select your GAN cube from the Bluetooth dialog
4. The cube visualization and information will appear in the browser

## Notes

- The first time you connect, you may need to enable experimental Web Platform features in Chrome:
  - Navigate to `chrome://flags/#enable-experimental-web-platform-features`
  - Enable the "Experimental Web Platform features" flag
  - Restart your browser
- If the MAC address cannot be automatically detected, you'll be prompted to enter it manually
- For best results, use on a laptop with built-in Bluetooth

## Files

- `cube-relay.html` - The standalone HTML application
- `README.md` - This file

All dependencies are loaded from CDNs, so an internet connection is required.