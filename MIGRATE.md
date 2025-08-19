# MIGRATE.md

Migration guide from WSL2 + Web Bluetooth to Native Windows + Native Bluetooth

## Overview

This document outlines the migration from the current WSL2 Ubuntu + Web Bluetooth implementation to a native Windows application using native Bluetooth APIs. The goal is to eliminate WSL2/Web Bluetooth bottlenecks while preserving all existing functionality.

## Current vs Target Architecture

### Current Architecture (WSL2 + Web Bluetooth)
```
[GAN Cube] ←--BLE--> [Chrome in WSL2] ←--WebSocket--> [Windows Python Bridge] ←--> [Game Input]
                     [Web Bluetooth API]              [windows_input_server.py]
                     [simple-bridge.html]
```

### Target Architecture (Native Windows)
```
[GAN Cube] ←--BLE--> [Native Windows Service] ←--WebSocket--> [Game Input Integration]
                     [Node.js + noble]                      [Integrated or External]
                     [HTTP Server + Dashboard]
```

## Migration Phases

### Phase 1: Environment Setup & Native Bluetooth

#### 1.1 Install Node.js Runtime (No Build Tools Required)
```bash
# Download Node.js Windows installer from nodejs.org
# Install Node.js 18+ LTS (includes npm)
node --version  # Verify installation
npm --version
```

#### 1.2 Install Native Bluetooth Dependencies
```bash
# Create new Windows project directory
mkdir gan-cube-native
cd gan-cube-native
npm init -y

# Install native Bluetooth libraries (no C++ compilation required)
npm install noble           # Windows native BLE library
npm install ws              # WebSocket server
npm install express         # HTTP server for dashboard
npm install aes-js          # AES encryption (same as current)
npm install rxjs            # Observable streams (same as current)

# Optional: Install as Windows service
npm install node-windows    # For running as Windows service
```

#### 1.3 Verify Bluetooth Capability
Create `test-bluetooth.js`:
```javascript
const noble = require('noble');

noble.on('stateChange', (state) => {
  console.log('Bluetooth state:', state);
  if (state === 'poweredOn') {
    console.log('✅ Native Bluetooth ready');
    noble.startScanning();
  }
});

noble.on('discover', (peripheral) => {
  if (peripheral.advertisement.localName?.includes('GAN')) {
    console.log('📱 Found GAN device:', peripheral.advertisement.localName);
    console.log('   MAC:', peripheral.address);
    console.log('   RSSI:', peripheral.rssi);
  }
});
```

### Phase 2: Protocol Logic Migration

#### 2.1 Port TypeScript Protocol Logic to Node.js

**Source Files to Convert:**
- `gan-web-bluetooth/src/gan-cube-definitions.ts` → `src/gan-cube-definitions.js`
- `gan-web-bluetooth/src/gan-cube-encrypter.ts` → `src/gan-cube-encrypter.js` 
- `gan-web-bluetooth/src/gan-cube-protocol.ts` → `src/gan-cube-protocol.js`
- `gan-web-bluetooth/src/utils.ts` → `src/utils.js`

**Key Migration Tasks:**
```javascript
// Example: Convert TypeScript definitions to JavaScript
// FROM: gan-cube-definitions.ts
const GAN_GEN2_SERVICE = '6e400001-b5a3-f393-e0a9-e50e24dcca9e';
const GAN_GEN2_WRITE = '6e400002-b5a3-f393-e0a9-e50e24dcca9e';
const GAN_GEN2_READ = '6e400003-b5a3-f393-e0a9-e50e24dcca9e';

// FROM: gan-cube-encrypter.ts  
const AES = require('aes-js');

class GanGen2CubeEncrypter {
  constructor(macAddress) {
    this.macAddress = macAddress;
    // Port AES key generation logic...
  }
  
  encrypt(data) {
    // Port encryption logic from TypeScript
  }
  
  decrypt(data) {
    // Port decryption logic from TypeScript  
  }
}
```

#### 2.2 Implement Native Bluetooth Connection Manager
Create `src/gan-cube-connection.js`:
```javascript
const noble = require('noble');
const { EventEmitter } = require('events');
const { GanGen2CubeEncrypter, GanGen3CubeEncrypter, GanGen4CubeEncrypter } = require('./gan-cube-encrypter');

class GanCubeConnection extends EventEmitter {
  constructor() {
    super();
    this.peripheral = null;
    this.encrypter = null;
    this.protocol = null;
  }

  async connect(deviceAddress) {
    // Implement native BLE connection using noble
    // Replace Web Bluetooth requestDevice() with noble scanning
    // Implement MAC address extraction from advertisement data
    // Auto-detect protocol generation (Gen2/Gen3/Gen4)
  }

  async sendCommand(command) {
    // Implement encrypted command sending via noble
  }

  handleNotification(data) {
    // Implement notification handling and event emission
  }
}
```

#### 2.3 Implement Protocol Drivers
Convert the existing protocol drivers:
- `GanGen2ProtocolDriver` 
- `GanGen3ProtocolDriver`
- `GanGen4ProtocolDriver`

Each driver needs to handle:
- Command encoding/decoding
- Move event parsing
- Orientation data processing
- Battery/status monitoring

### Phase 3: Dashboard Integration

#### 3.1 Create HTTP Server for Dashboard
Create `src/dashboard-server.js`:
```javascript
const express = require('express');
const WebSocket = require('ws');
const path = require('path');

class DashboardServer {
  constructor() {
    this.app = express();
    this.wss = new WebSocket.Server({ port: 8080 });
    this.cubeConnection = null;
  }

  start() {
    // Serve static files (HTML dashboard)
    this.app.use(express.static(path.join(__dirname, '../dashboard')));
    
    // WebSocket for real-time communication
    this.wss.on('connection', (ws) => {
      // Handle dashboard WebSocket messages
      ws.on('message', (message) => {
        const data = JSON.parse(message);
        this.handleDashboardMessage(data, ws);
      });
    });

    this.app.listen(3000, () => {
      console.log('Dashboard server running on http://localhost:3000');
    });
  }

  handleDashboardMessage(data, ws) {
    switch(data.type) {
      case 'CONNECT_CUBE':
        this.connectToCube().then(() => {
          ws.send(JSON.stringify({ type: 'CUBE_CONNECTED' }));
        });
        break;
      case 'DISCONNECT_CUBE':
        this.disconnectFromCube();
        break;
      // Handle other dashboard commands
    }
  }
}
```

#### 3.2 Modify Dashboard HTML
**Copy and modify `simple-bridge.html` → `dashboard/index.html`:**

**Key Changes:**
```html
<!-- REMOVE Web Bluetooth code -->
<!-- <script type="module" src="https://cdn.skypack.dev/gan-web-bluetooth@3"></script> -->

<!-- REPLACE with WebSocket connection -->
<script>
// Replace Web Bluetooth connection with WebSocket
class NativeCubeConnection {
  constructor() {
    this.ws = new WebSocket('ws://localhost:8080');
    this.connected = false;
    
    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.handleMessage(data);
    };
  }

  connectCube() {
    // Send WebSocket message instead of Web Bluetooth request
    this.ws.send(JSON.stringify({ type: 'CONNECT_CUBE' }));
  }

  handleMessage(data) {
    // Handle cube events from native service
    switch(data.type) {
      case 'MOVE':
        this.onMove(data);
        break;
      case 'ORIENTATION':
        this.onOrientation(data);
        break;
      case 'BATTERY':
        this.onBattery(data);
        break;
    }
  }
}
</script>
```

### Phase 4: Input Injection Integration

#### 4.1 Option A: Integrate with Existing Python Bridge
```javascript
// In main service, forward events to existing windows_input_server.py
const WebSocket = require('ws');

class InputBridge {
  constructor() {
    this.inputWs = new WebSocket('ws://localhost:8082'); // windows_input_server.py port
  }

  sendMove(moveData) {
    this.inputWs.send(JSON.stringify({
      type: 'MOVE',
      move: moveData.move,
      timestamp: Date.now()
    }));
  }

  sendOrientation(orientationData) {
    this.inputWs.send(JSON.stringify({
      type: 'ORIENTATION',
      tiltX: orientationData.tiltX,
      tiltY: orientationData.tiltY,
      spinZ: orientationData.spinZ
    }));
  }
}
```

#### 4.2 Option B: Native Node.js Input Injection
```bash
# Install native Windows input library
npm install robotjs  # Cross-platform input automation
npm install node-key-sender  # Windows-specific key sending
```

```javascript
const robot = require('robotjs');

class NativeInputInjector {
  sendKeyPress(key) {
    robot.keyTap(key);
  }

  sendMouseClick(button) {
    robot.mouseClick(button);
  }

  sendMouseMove(x, y) {
    robot.moveMouse(x, y);
  }
}
```

### Phase 5: Service Architecture & Main Application

#### 5.1 Create Main Service Entry Point
Create `src/main.js`:
```javascript
const { GanCubeConnection } = require('./gan-cube-connection');
const { DashboardServer } = require('./dashboard-server');
const { InputBridge } = require('./input-bridge');

class GanCubeNativeService {
  constructor() {
    this.cubeConnection = new GanCubeConnection();
    this.dashboardServer = new DashboardServer();
    this.inputBridge = new InputBridge();
    
    this.setupEventHandlers();
  }

  setupEventHandlers() {
    // Forward cube events to dashboard
    this.cubeConnection.on('move', (data) => {
      this.dashboardServer.broadcast({ type: 'MOVE', ...data });
      this.inputBridge.sendMove(data);
    });

    this.cubeConnection.on('orientation', (data) => {
      this.dashboardServer.broadcast({ type: 'ORIENTATION', ...data });
      this.inputBridge.sendOrientation(data);
    });

    this.cubeConnection.on('battery', (data) => {
      this.dashboardServer.broadcast({ type: 'BATTERY', ...data });
    });
  }

  async start() {
    console.log('🚀 Starting GAN Cube Native Service...');
    
    // Start dashboard server
    await this.dashboardServer.start();
    console.log('✅ Dashboard server started on http://localhost:3000');
    
    // Initialize Bluetooth
    await this.cubeConnection.initialize();
    console.log('✅ Native Bluetooth initialized');
    
    console.log('🎮 Ready for cube connection!');
  }
}

// Start service
const service = new GanCubeNativeService();
service.start().catch(console.error);
```

#### 5.2 Windows Service Installation
```javascript
// install-service.js
const Service = require('node-windows').Service;

const svc = new Service({
  name: 'GAN Cube Controller',
  description: 'Native Windows service for GAN Cube gaming controller',
  script: 'C:\\path\\to\\gan-cube-native\\src\\main.js'
});

svc.on('install', () => {
  console.log('Service installed');
  svc.start();
});

svc.install();
```

### Phase 6: Testing & Validation

#### 6.1 Feature Parity Checklist
- [ ] **Bluetooth Connection**: Native connection to GAN356 i3, GAN12, etc.
- [ ] **Move Detection**: All face moves (R, L, U, D, F, B) with directions
- [ ] **Orientation Tracking**: Real-time tilt and rotation data
- [ ] **Battery Monitoring**: Battery level reporting
- [ ] **Encryption**: AES encryption for all supported protocols
- [ ] **Dashboard**: Web interface with 3D visualization
- [ ] **Input Injection**: Gaming input (keyboard, mouse, gamepad)
- [ ] **Multiple Protocols**: Gen2, Gen3, Gen4 support
- [ ] **MAC Address Handling**: Automatic extraction and key salting

#### 6.2 Performance Testing
```javascript
// performance-test.js
const { performance } = require('perf_hooks');

class LatencyTester {
  measureCubeToInput() {
    const start = performance.now();
    
    cubeConnection.once('move', (data) => {
      const end = performance.now();
      console.log(`Cube → Input latency: ${end - start}ms`);
    });
  }
}
```

#### 6.3 Migration Testing Steps
1. **Parallel Testing**: Run both systems simultaneously for comparison
2. **Latency Comparison**: Measure WSL2 vs Native latency
3. **Stability Testing**: Long-duration connection testing
4. **Gaming Integration**: Test with actual games (Elden Ring, etc.)
5. **Multi-cube Testing**: Ensure single/multiple cube support

### Phase 7: Deployment & Distribution

#### 7.1 Packaging for Distribution
```bash
# Create standalone executable
npm install -g pkg
pkg src/main.js --targets node18-win-x64 --output gan-cube-native.exe

# Create installer
npm install -g electron-builder
# Create installer package with dashboard files
```

#### 7.2 User Migration Guide
```markdown
## For End Users:

### Uninstall Old System:
1. Stop WSL2: `wsl --shutdown`
2. Remove WSL2 Ubuntu distribution
3. Uninstall Docker Desktop (if only used for WSL2)

### Install New System:
1. Download `gan-cube-native-installer.exe`
2. Run installer (installs Node.js if needed)
3. Service starts automatically
4. Open http://localhost:3000 for dashboard
5. Click "Connect Cube" - same as before!

### Verify Migration:
- Same dashboard interface
- Same gaming controls
- Better latency (<10ms vs ~50ms)
- No WSL2 dependency
```

## Expected Performance Improvements

| Metric | WSL2 + Web Bluetooth | Native Windows |
|--------|---------------------|----------------|
| **Cube → Input Latency** | 30-80ms | 5-15ms |
| **Connection Stability** | Moderate | High |
| **CPU Usage** | High (Chrome + WSL2) | Low |
| **Memory Usage** | 500MB+ | 50-100MB |
| **Boot Time** | 30-60s | 5-10s |
| **Reliability** | WSL2 dependent | Native |

## Risk Mitigation

### Fallback Plan
- Keep WSL2 system available during migration
- Gradual migration with parallel testing
- Easy rollback if issues discovered

### Known Challenges
1. **Bluetooth Driver Compatibility**: Test on various Windows versions
2. **Noble Library Limitations**: May need alternative if issues found
3. **Windows Security**: May require UAC elevation for input injection
4. **Antivirus False Positives**: Input automation may trigger warnings

## Conclusion

This migration eliminates WSL2 dependencies while maintaining full functionality and improving performance. The modular approach allows gradual migration and easy rollback if needed. The native Windows service provides better integration, lower latency, and improved reliability for gaming applications.