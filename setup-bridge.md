# GAN Cube → WSL Bridge Setup

## Quick Start

### 1. Install Node.js in WSL (if not already installed)
```bash
# Check if Node.js is installed
node --version

# If not installed:
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs
```

### 2. Install WebSocket dependency
```bash
cd /home/mm/mykl/rubiks
npm install ws
```

### 3. Start the WSL receiver
```bash
node wsl-cube-receiver.js
```
You should see:
```
🎲 GAN Cube Terminal Receiver
Starting WebSocket server on ws://localhost:8080
✅ WebSocket server ready!
Waiting for browser connection...
```

### 4. Set up the browser side

**Option A: Use your existing gan-web-bluetooth setup**
- Copy `cube-bridge.html` to your `gan-web-bluetooth` directory
- Modify the script section to import the actual library:
```javascript
const { connectGanCube } = await import('./dist/esm/index.mjs');
```

**Option B: Test with simulation first**
- Open `cube-bridge.html` directly in Chrome
- Click "Connect to WSL" - should show connection in terminal
- Click "Connect GAN Cube" - will simulate moves for testing

### 5. Test the connection
1. WSL terminal should show: `🔗 Browser connected from ::ffff:172.x.x.x`
2. Browser should show: `Status: WebSocket Connected`
3. Simulated moves will appear in terminal like:
```
[3:45:12 PM] 🔴 Move #1: R (15ms latency)
[3:45:14 PM] 🔴 Move #2: R' (12ms latency)
```

## Next Steps

### To use with real GAN cube:
1. Build your `gan-web-bluetooth` library:
```bash
cd gan-web-bluetooth
npm run build
```

2. Update `cube-bridge.html` script section to import real library
3. Replace the simulation code with actual cube connection code

### Troubleshooting:
- **"EADDRINUSE"**: Kill existing process with `pkill -f wsl-cube-receiver`
- **WebSocket connection fails**: Check Windows Firewall, try `localhost` instead of `0.0.0.0`
- **No cube detection**: Ensure cube is charged and in pairing mode

The bridge currently simulates cube moves every 2 seconds for testing. Once working, replace with your actual gan-web-bluetooth integration!