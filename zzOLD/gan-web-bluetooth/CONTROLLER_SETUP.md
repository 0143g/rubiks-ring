# 🎮 GAN Cube Gaming Controller Setup

## 🚀 Quick Start (Windows)

### Step 1: Install Python Dependencies
```bash
pip install websockets pywin32
```

### Step 2: Start the Controller Bridge
```bash
python cube_controller_bridge.py
```
You should see:
```
Platform: Windows (win32api)
Starting GAN Cube Controller Bridge on port 8081
Waiting for browser connection...
```

### Step 3: Open Browser Interface
1. Open `simple-bridge.html` in Chrome/Edge
2. Click **"Connect Controller Bridge"** 
3. Click **"Connect Cube"** and select your GAN356 i3
4. Click **"Reset Orientation"** to set neutral position

### Step 4: Test in Game
1. Launch Elden Ring (or any game)
2. Perform cube moves:
   - **R move** → Left click (attack)
   - **R' move** → Right click 
   - **Tilt cube forward** → W key (move forward)
   - **Tilt cube left/right** → A/D keys (strafe)
   - **Rotate cube (yaw)** → Mouse look

## 🐧 Linux Setup
```bash
pip install websockets python-xlib
python cube_controller_bridge.py
```

## 🍎 macOS Setup  
```bash
pip install websockets pyobjc
python cube_controller_bridge.py
```

## 🎯 Gaming Controls

### Discrete Moves (Face Rotations)
| Cube Move | Game Action | Description |
|-----------|-------------|-------------|
| R | Left Click | Primary attack/interact |
| R' | Right Click | Secondary attack/block |
| L | A Key | Strafe left |
| L' | D Key | Strafe right |

### Continuous Controls (Orientation)
| Cube Tilt | Game Action | Description |
|-----------|-------------|-------------|
| Forward Tilt | W Key | Move forward |
| Backward Tilt | S Key | Move backward |
| Left Tilt | A Key | Strafe left |
| Right Tilt | D Key | Strafe right |
| Yaw Rotation | Mouse X | Camera look |

## ⚙️ Configuration

Edit these values in `simple-bridge.html`:

### Movement Sensitivity
```javascript
movement: {
    deadzone: 0.15,        // Ignore small tilts (0.0-1.0)
    sensitivity: 2.0,      // Movement response (1.0-5.0)
}
```

### Camera Sensitivity  
```javascript
camera: {
    sensitivity: 150,      // Mouse pixels per radian (50-300)
    deadzone: 0.1,        // Mouse deadzone (0.0-0.5)
}
```

### Add More Moves
```javascript
const MOVE_MAPPINGS = {
    'U': { type: 'key', action: 'Space', char: ' ', description: 'Jump' },
    'F': { type: 'key', action: 'ShiftLeft', char: 'Shift', description: 'Sprint' },
    // Add any cube move → any key/click
};
```

## 🎮 Game-Specific Configs

### FPS Games (CS2, Valorant)
- R = Shoot, R' = ADS
- Orientation = Movement + mouse look
- Add U = Jump, F = Reload

### Racing Games
- Forward/back tilt = Accelerate/brake
- Left/right tilt = Steering
- R/R' = Gear shifts

### Flight Simulators  
- Full 6DOF control via orientation
- Face moves = Landing gear, flaps, etc.

## 🔧 Troubleshooting

### "Controller bridge not connected"
- Ensure Python script is running
- Check firewall isn't blocking port 8081
- Try restarting the bridge

### "Mouse/keyboard not working in game"
- Make sure bridge is connected (purple button should show connected)
- Some games need to be run as administrator
- Check if game has input blocking (fullscreen vs windowed)

### "Orientation too sensitive/not sensitive enough" 
- Adjust `sensitivity` values in config
- Use "Reset Orientation" to recalibrate neutral position

## 🚀 Advanced: AutoHotkey Alternative (Windows)

For even lower latency, use the AutoHotkey version:

1. Install [AutoHotkey](https://www.autohotkey.com/)
2. Download [WebSocket.ahk library](https://github.com/G33kDude/WebSocket.ahk)
3. Run `cube-controller.ahk`

## 🎯 Performance Tips

1. **Close unnecessary browser tabs** - reduces CPU usage
2. **Use Fullscreen games** - better input capture  
3. **Disable browser extensions** - prevents interference
4. **Run as administrator** - some games require elevated permissions

---

**🎮 Your GAN356 i3 is now a professional gaming controller!**

Works with any game that accepts keyboard/mouse input:
- All FPS games
- Racing simulators  
- Flight sims
- Strategy games
- And more!