# GAN Smart Cube Dashboard

A modern web-based dashboard for monitoring and controlling GAN Smart Cubes using the Python implementation.

## Features

### 🎲 Real-Time Cube Monitoring
- **Live move detection** with clean notation (R, U', F, etc.)
- **Move history** with timestamps
- **Cube state visualization** in Kociemba format
- **Real-time orientation** tracking with quaternions
- **Battery level** monitoring with visual indicator

### 🌐 Web Interface
- **Responsive design** that works on desktop and mobile
- **Real-time updates** via WebSocket connection
- **Clean, modern UI** with gradient backgrounds and smooth animations
- **Connection status** indicators and controls
- **Statistics panel** with session tracking

### 🔧 Dashboard Controls
- **Connect/Disconnect** cube with one click
- **Request state** and battery information
- **Clear move history** 
- **Real-time connection monitoring**

## Quick Start

### 1. Install Dependencies

```bash
pip install flask flask-socketio python-socketio
```

Or install all requirements:
```bash
pip install -r requirements.txt
```

### 2. Run the Dashboard

```bash
python cube_dashboard.py
```

The dashboard will be available at: **http://localhost:5000**

### 3. Connect Your Cube

1. **Open the dashboard** in your web browser
2. **Click "Connect Cube"** - it will automatically scan for GAN cubes
3. **Make moves** on your cube to see real-time updates
4. **Monitor** all cube activity in the web interface

## Dashboard Layout

### Status Bar
- **Connection controls** (Connect/Disconnect/Request Info)
- **Connection status** with visual indicators
- **Cube information** (Model, Firmware, Total Moves)
- **Battery indicator** with colored progress bar

### Main Panels

#### 🎯 Move History
- Shows last 20 moves with timestamps
- Displays move notation (R, U', F2, etc.)
- Real-time updates as you turn the cube
- Scrollable history view

#### 🌐 Cube Orientation  
- Live quaternion values (X, Y, Z, W)
- Real-time orientation tracking
- 3D visualization placeholder (ready for future enhancement)
- Smooth value updates

#### 📋 Cube State
- Current facelets state in Kociemba format
- Serial number tracking
- Last update timestamp
- Full 54-character state string

#### 📊 Statistics
- Session move counter
- Last move performed
- Connection duration
- Protocol version information

## Technical Architecture

### Backend (Python)
```
cube_dashboard.py
├── Flask web server
├── SocketIO for real-time communication  
├── Async cube connection handling
├── Event processing and forwarding
└── Thread management for cube operations
```

### Frontend (JavaScript)
```
dashboard.html
├── Socket.IO client for real-time updates
├── Modern responsive CSS with animations
├── Real-time data visualization
├── Interactive controls and status indicators
└── Message notifications system
```

### Communication Flow
```
GAN Cube → Python Library → Dashboard Server → WebSocket → Browser
```

## WebSocket Events

### Client → Server
- `connect_cube` - Initiate cube connection
- `disconnect_cube` - Disconnect from cube
- `request_state` - Request current cube state
- `request_battery` - Request battery level
- `clear_history` - Clear move history

### Server → Client
- `status` - Connection status updates
- `move` - New move detected
- `move_history` - Move history update
- `facelets` - Cube state update
- `orientation` - Orientation change
- `battery` - Battery level update
- `hardware` - Device information
- `message` - Status messages

## Features in Detail

### Real-Time Move Detection
```javascript
socket.on('move', (data) => {
    // data.move = "R", "U'", "F2", etc.
    // data.face = 0-5 (U,R,F,D,L,B)
    // data.direction = 0 (CW) or 1 (CCW)
    // data.timestamp = host timestamp
    // data.cube_timestamp = cube internal time
});
```

### Connection Status Monitoring
- **Green dot**: Connected and active
- **Yellow dot (pulsing)**: Connecting...
- **Red dot**: Disconnected
- **Red dot (flashing)**: Connection error

### Battery Monitoring
- **Green**: >60% battery
- **Orange**: 30-60% battery  
- **Red**: <30% battery
- **Visual progress bar** with percentage

### Move History
- Displays up to 50 moves (keeps last 50)
- Shows most recent moves at top
- Includes precise timestamps
- Real-time updates as you turn cube

## Customization

### Styling
Edit `templates/dashboard.html` CSS section to customize:
- Colors and gradients
- Panel layouts
- Animation effects
- Responsive breakpoints

### Functionality
Edit `cube_dashboard.py` to:
- Add new WebSocket events
- Modify data processing
- Add cube commands
- Extend statistics tracking

## Troubleshooting

### Dashboard Won't Start
```bash
# Check if dependencies are installed
pip install flask flask-socketio

# Check if port 5000 is available
lsof -i :5000

# Run with debug mode
python cube_dashboard.py
```

### Cube Won't Connect
1. **Check Bluetooth** - Ensure Bluetooth is enabled
2. **Check cube battery** - Low battery affects connection
3. **Check distance** - Move closer to computer
4. **Restart cube** - Turn cube off/on
5. **Check console** - Look for error messages

### Browser Issues
1. **Refresh page** - Clear any cached WebSocket connections
2. **Check browser console** - Look for JavaScript errors
3. **Try different browser** - Chrome/Edge work best
4. **Check network** - Ensure localhost access

### Performance Issues
- **Limit orientation updates** - High-frequency gyro data can cause lag
- **Clear move history** regularly for long sessions
- **Close other tabs** using WebSocket connections

## Development

### Adding New Features

1. **Backend**: Add event handlers in `cube_dashboard.py`
2. **Frontend**: Add UI elements and WebSocket listeners in `dashboard.html`
3. **Communication**: Define new WebSocket events for data exchange

### Example: Adding New Panel
```python
# Backend: Add data processing
def _handle_new_event(self, event):
    data = {'value': event.data, 'timestamp': now()}
    self.socketio.emit('new_event', data)

# Frontend: Add UI update
socket.on('new_event', (data) => {
    document.getElementById('newValue').textContent = data.value;
});
```

## Comparison to TypeScript Version

| Feature | TypeScript (simple-bridge.html) | Python Dashboard |
|---------|----------------------------------|------------------|
| **Platform** | Browser + Web Bluetooth | Python + Flask |
| **Connection** | Direct browser Bluetooth | Python bleak library |
| **Real-time** | Direct WebSocket | Flask-SocketIO |
| **UI Framework** | Vanilla HTML/JS | Flask templates |
| **Cube Support** | Gen2/Gen3/Gen4 | Gen2 (primary) |
| **Move Detection** | ✅ | ✅ |
| **Orientation** | ✅ | ✅ |
| **Battery** | ✅ | ✅ |
| **State Display** | ✅ | ✅ |
| **3D Visualization** | Basic | Placeholder |

## Future Enhancements

### Planned Features
- **3D cube visualization** using Three.js
- **Solve timer** integration
- **Algorithm trainer** mode
- **Multiple cube support**
- **Data export** (CSV, JSON)
- **Cube configuration** settings

### Advanced Features
- **Machine learning** move prediction
- **Pattern recognition** and analysis
- **Scramble generation** and verification
- **Competition mode** with official timer
- **Cloud synchronization** for move history

The dashboard provides a solid foundation for cube monitoring and can be easily extended with additional features as needed.
