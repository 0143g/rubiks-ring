# GAN Cube Native Windows Controller

A native Windows implementation of the GAN Smart Cube controller system using Node.js and native Bluetooth APIs. This eliminates the need for WSL2 and Web Bluetooth, providing ultra-low latency gaming controller functionality.

## 🚀 Quick Start

### Prerequisites
- **Node.js 18+** - Download from [nodejs.org](https://nodejs.org/)
- **Windows 10/11** with working Bluetooth adapter
- **GAN Smart Cube** (Gen2, Gen3, or Gen4 supported)

### Installation

1. **Extract and Navigate**
   ```cmd
   cd windows-port
   ```

2. **Install Dependencies**
   ```cmd
   install-dependencies.bat
   ```
   Or manually:
   ```cmd
   npm install
   ```

3. **Test Bluetooth**
   ```cmd
   test-bluetooth.bat
   ```

4. **Start the Service**
   ```cmd
   start-native-service.bat
   ```

5. **Open Dashboard**
   - Open http://localhost:3000 in Chrome/Edge
   - Click "Connect Cube" to find your GAN cube
   - Click "Connect Controller Bridge" for gaming input

## 🎮 Gaming Setup

### Option A: Existing Python Bridge (Recommended)
1. Start the native service: `start-native-service.bat`
2. In another terminal, run your existing Python bridge:
   ```cmd
   python windows_input_server.py
   ```
3. Connect cube via dashboard
4. Gaming input will work through the Python bridge

### Option B: Native Only (Future)
The native service provides WebSocket API on port 8082 for gaming input. Your existing Python bridge can connect to this instead of WSL2.

## 🔧 Architecture

```
[GAN Cube] ←--BLE--> [Native Node.js Service] ←--WebSocket--> [Python Gaming Bridge]
                     │                                        │
                     ├─ Dashboard (Port 3000)                └─ Game Input
                     ├─ WebSocket API (Port 8080)               (Keyboard/Mouse/Gamepad)
                     └─ Input Bridge (Port 8082)
```

## 📡 API Endpoints

### WebSocket API (ws://localhost:8080)
Dashboard communication:
- `CONNECT_CUBE` - Connect to first available cube
- `SCAN_CUBES` - Start scanning for cubes
- `DISCONNECT_CUBE` - Disconnect current cube

### Input Bridge API (ws://localhost:8082)
Gaming input communication:
- Receives `MOVE` events with cube moves
- Receives `ORIENTATION` events with tilt data
- Compatible with existing Python bridge system

### HTTP API (http://localhost:3000)
- `/` - Dashboard interface
- `/api/status` - Service status
- `/health` - Health check

## 🎲 Supported Cubes

### GAN Gen2 Protocol
- GAN Mini ui FreePlay
- GAN12 ui FreePlay  
- GAN12 ui
- GAN356 i Carry S
- GAN356 i Carry
- GAN356 i 3
- Monster Go 3Ai
- MoYu AI 2023

### GAN Gen3 Protocol
- GAN356 i Carry 2

### GAN Gen4 Protocol
- GAN12 ui Maglev
- GAN14 ui FreePlay

## 🔧 Configuration

### Move Mappings
Default controller mappings:
- **R** → Right Bumper (R1)
- **R'** → Right Trigger (R2)
- **L/L'** → B Button
- **D** → X Button
- **B** → Right Stick Press (R3)
- **Cube Tilt** → Left Analog Stick

### Orientation Control
- **Forward/Back Tilt** → W/S keys or Left Stick Y
- **Left/Right Tilt** → A/D keys or Left Stick X
- **Rotation** → Mouse or Right Stick X

## 🛠️ Troubleshooting

### Bluetooth Issues
- Run `test-bluetooth.bat` to verify Bluetooth works
- Ensure Bluetooth is enabled in Windows Settings
- Check no other apps are using Bluetooth exclusively
- Try restarting Bluetooth service in Windows

### Connection Issues
- Make sure cube is charged and in pairing mode
- Try scanning multiple times - cubes don't always advertise consistently
- Check Windows Bluetooth permissions for Node.js

### Gaming Input Issues
- Ensure `windows_input_server.py` is running
- Check WebSocket connection on port 8082
- Verify Python bridge has proper permissions
- Test with simple games first (e.g., Notepad for keyboard input)

### Performance Issues
- Close other Bluetooth applications
- Ensure Windows is not in power saving mode
- Check Task Manager for high CPU usage processes

## 🔍 Monitoring

### Service Status
Check console output for:
- ✅ Bluetooth initialization
- 📡 Cube connection status  
- 🎮 Input bridge connectivity
- 📊 Event processing rates

### Dashboard
The web dashboard shows:
- Real-time cube orientation
- Battery level and hardware info
- Move detection and history
- Connection status for all components

### Debug Mode
Run with additional logging:
```cmd
node src/main.js --status
```

## 🚨 Common Issues

### "Node.js not found"
Install Node.js from [nodejs.org](https://nodejs.org/) and restart your command prompt.

### "Bluetooth not ready"
1. Check Windows Settings → Bluetooth & devices
2. Ensure adapter is enabled
3. Try running as Administrator
4. Restart Bluetooth service: `services.msc` → Bluetooth Support Service → Restart

### "Noble installation failed"  
This system uses @stoprocent/noble fork for better Windows compatibility. If installation fails:
```cmd
npm install --global windows-build-tools
```
Or install Visual Studio Build Tools manually.

### "Cube not found"
1. Ensure cube is charged (>20% battery)
2. Put cube in pairing mode (twist randomly for a few seconds)
3. Try scanning multiple times
4. Check cube isn't connected to another device

## 📈 Performance

Expected performance improvements over WSL2 + Web Bluetooth:
- **Latency**: 5-15ms (vs 30-80ms)  
- **CPU Usage**: ~50MB RAM (vs 500MB+)
- **Reliability**: Native Windows APIs
- **Boot Time**: 2-5 seconds (vs 30-60s)

## 🔄 Migration from WSL2

If you're migrating from the WSL2 system:
1. Stop WSL2: `wsl --shutdown`
2. Install this native system
3. Update your Python bridge to connect to `localhost:8082` instead of WSL2
4. Test with existing games - same controller mappings

## 📄 License

MIT License - Same as the original GAN Web Bluetooth library

## 🤝 Contributing

This is a native Windows port of the TypeScript GAN Web Bluetooth library. All cube protocol logic, encryption, and communication patterns are preserved from the original implementation.