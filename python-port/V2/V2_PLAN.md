# V2 Implementation Plan - Direct Cube Controller

## Goal
Create a single, high-performance Python application that directly connects the GAN356 i 3 cube to a virtual gamepad with realistic low latency (30-40ms average, <100ms max).

## Reality Check
- **Cube sends gyro data at 15-20Hz** (50-66ms between updates)
- **BLE minimum latency: 7.5-30ms** (connection interval)
- **Realistic total latency: 30-40ms** (cube interval + BLE + processing)
- **Focus: Eliminate processing overhead, not fight physics**

## Core Architecture

### Single File: `cube_controller_v2.py`
All functionality in one async Python file to eliminate IPC overhead and simplify data flow.

```
GAN Cube → [BLE/bleak] → Event Handler → State Machine → [vgamepad] → Game
```

## Implementation Steps

### Step 1: Core Bluetooth Connection
**File:** `cube_controller_v2.py`
**Time:** 2 hours

```python
class CubeControllerV2:
    def __init__(self):
        self.client = None  # BleakClient
        self.gamepad = vg.VX360Gamepad()
        self.config = self.load_config()
        
    async def connect_cube(self, address=None):
        # Direct BLE connection using bleak
        # Reuse encryption logic from gan_web_bluetooth
        # Subscribe to notifications immediately
```

**Key Points:**
- Copy encryption setup from `gan_web_bluetooth/smart_cube.py:149-186`
- Use Gen2 protocol only (our cube is GAN356 i)
- No intermediate queues or buffers

### Step 2: Direct Event Processing with Duplicate Filtering
**Time:** 2 hours

```python
async def _handle_notification(self, sender, data):
    # Decrypt data inline
    decrypted = self.encrypter.decrypt(data)
    
    # Parse message type (first 4 bits)
    msg_type = (decrypted[0] >> 4) & 0x0F
    
    if msg_type == 0x02:  # MOVE
        if not self.duplicate_filter.is_duplicate_move(decrypted):
            self._process_move_immediate(decrypted)
    elif msg_type == 0x01:  # ORIENTATION
        self._process_orientation_immediate(decrypted)

class DuplicateFilter:
    def __init__(self):
        self.last_move_data = None
        self.last_move_time = 0
        
    def is_duplicate_move(self, data):
        now_ms = time.perf_counter_ns() // 1_000_000
        # Same move within 50ms = duplicate
        if data == self.last_move_data and (now_ms - self.last_move_time) < 50:
            return True
        self.last_move_data = data
        self.last_move_time = now_ms
        return False
```

**Key Points:**
- Filter duplicate moves (cube sometimes double-sends)
- NO async/await in processing functions
- Process data in-place without copying

### Step 3: Optimized Move Processing
**Time:** 1 hour

```python
def _process_move_immediate(self, data):
    # Extract move directly (bits 4-11)
    move_id = ((data[0] & 0x0F) << 4) | ((data[1] >> 4) & 0x0F)
    move = MOVE_MAP[move_id]  # Pre-computed lookup table
    
    # Get action from config
    action = self.config['moves'].get(move)
    if not action:
        return
    
    # Execute immediately
    if action.startswith('gamepad_'):
        self._execute_gamepad_action(action)
```

**Key Points:**
- Pre-compute all move mappings at startup
- No string operations in hot path
- Direct gamepad manipulation

### Step 4: Gamepad Batching (Critical Optimization)
**Time:** 2 hours

```python
class GamepadBatcher:
    """Batch gamepad updates to avoid calling update() too often"""
    def __init__(self, gamepad):
        self.gamepad = gamepad
        self.dirty = False
        self.current_orientation = None
        self.last_flush = 0
        
    def update_orientation(self, quaternion):
        # Always update internal state immediately
        self.current_orientation = quaternion
        x, y, z = self.quaternion_to_joystick(quaternion)
        self.gamepad.left_joystick_float(x, y)
        self.gamepad.right_joystick_float(z, 0)
        self.dirty = True
        # Don't call update() here!
        
    def press_button(self, button):
        self.gamepad.press_button(button)
        self.dirty = True
        # Don't call update() here!
        
    async def flush_loop(self):
        """Run this as a background task"""
        while True:
            if self.dirty:
                self.gamepad.update()  # Single update call
                self.dirty = False
            await asyncio.sleep(0.008)  # 125Hz flush rate
```

**Key Points:**
- **vgamepad.update() is expensive** - batch all changes
- Process every orientation immediately (don't drop data)
- Flush gamepad at fixed 125Hz rate
- This alone can reduce latency by 10-20ms

### Step 5: Sprint Mode State Machine (Non-blocking)
**Time:** 1 hour

```python
class SprintStateMachine:
    def __init__(self, gamepad_batcher):
        self.batcher = gamepad_batcher
        self.sprinting = False
        self.rolling = False
        
    def handle_orientation(self, tilt_y):
        # Simple threshold check
        should_sprint = tilt_y > 0.7
        
        if should_sprint and not self.sprinting and not self.rolling:
            self.start_sprint()
        elif not should_sprint and self.sprinting and not self.rolling:
            self.stop_sprint()
            
    async def handle_roll(self):
        if self.sprinting and not self.rolling:
            # Non-blocking roll sequence
            self.rolling = True
            self.batcher.release_button(B)
            await asyncio.sleep(0.05)  # Non-blocking!
            self.batcher.press_button(B)
            await asyncio.sleep(0.1)
            self.batcher.release_button(B)
            await asyncio.sleep(0.05)
            if self.sprinting:  # Re-check after roll
                self.batcher.press_button(B)
            self.rolling = False
```

**Key Points:**
- Use async/await for timing (non-blocking)
- Work through GamepadBatcher for efficiency
- Prevent concurrent rolls with flag

### Step 6: Configuration & Error Handling
**Time:** 1 hour

```python
def load_config(self):
    # Load and validate config
    # Pre-compute all lookups
    # Convert string mappings to button constants
    
def reconnect_loop(self):
    while True:
        try:
            await self.connect_cube()
            await self.process_events()
        except Exception as e:
            print(f"Connection lost: {e}")
            await asyncio.sleep(1)
            # Exponential backoff...
```

### Step 7: Performance Monitoring
**Time:** 30 minutes

```python
class PerformanceMonitor:
    def __init__(self):
        self.latencies = deque(maxlen=100)
        self.last_report = 0
        
    def record_latency(self, start_ns):
        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        self.latencies.append(latency_ms)
        
        # Report every second
        now = time.time()
        if now - self.last_report > 1.0:
            avg = sum(self.latencies) / len(self.latencies)
            max_lat = max(self.latencies)
            if avg > 10 or max_lat > 50:
                print(f"⚠️ Latency: avg={avg:.1f}ms max={max_lat:.1f}ms")
            self.last_report = now
```

## File Structure

```
V2/
├── cube_controller_v2.py      # Main application (single file)
├── config.json                # Configuration (copy from parent)
├── requirements.txt           # Minimal dependencies
└── README.md                  # Usage instructions
```

## Dependencies

### Required
```
bleak==0.21.1          # Bluetooth LE
vgamepad==0.1.0        # Virtual gamepad (Windows)
pycryptodome==3.20.0   # AES encryption for cube protocol
```

### NOT Required (removed bottlenecks)
```
# flask              ❌ No web server
# flask-socketio     ❌ No WebSocket server
# websockets         ❌ No IPC
# threading          ❌ Pure async
# queue              ❌ No queuing
# psutil             ❌ No diagnostics overhead
```

## Performance Targets (Realistic)

| Metric | Current V1 | Target V2 | Method |
|--------|------------|-----------|--------|
| Avg Latency | 60-80ms | 30-40ms | Direct processing + batching |
| Max Latency | 600ms | <100ms | No queues, handle BLE hiccups |
| CPU Usage | 15-20% | <3% | Efficient event loop |
| Memory | 256MB | <30MB | No buffers |
| Code Size | ~2000 lines | <600 lines | Single file |

## Why These Targets Are Realistic

1. **Cube hardware limit**: 15-20Hz = 50-66ms between updates
2. **BLE protocol overhead**: 7.5-30ms connection interval
3. **Our optimization**: <10ms processing (achievable!)
4. **Total**: 50-66ms (cube) + 15ms (BLE avg) + 5ms (processing) = ~70ms worst case, 30-40ms typical

## Testing Plan

### Phase 1: Basic Functionality (30 min)
1. Connect to cube
2. Verify move detection
3. Test button mappings
4. Check reconnection

### Phase 2: Performance Testing (30 min)
1. Measure end-to-end latency
2. Monitor CPU/memory usage
3. Test under rapid input
4. Verify no input drops

### Phase 3: Game Testing (1 hour)
1. Test with Elden Ring (original use case)
2. Verify sprint/roll mechanics
3. Test orientation controls
4. Extended play session (1+ hours)

## Risk Mitigation

### Risk 1: Bluetooth Instability
**Solution:** Exponential backoff reconnection with state preservation

### Risk 2: Gamepad Driver Issues
**Solution:** Defensive error handling, fallback to keyboard if needed

### Risk 3: Timing Precision
**Solution:** Use `time.perf_counter_ns()` for nanosecond precision

## Success Criteria

- [ ] Connect to cube in <2 seconds
- [ ] Process moves in <5ms
- [ ] Process orientation in <5ms  
- [ ] Zero duplicate moves processed
- [ ] Gamepad batch updates at 125Hz
- [ ] Total latency 30-40ms average
- [ ] Stable for 8+ hour sessions
- [ ] CPU usage <3%
- [ ] Memory usage <30MB
- [ ] Code under 600 lines

## Next Actions (Revised Order)

1. **NOW**: Create `cube_controller_v2.py` skeleton
2. **+30min**: Basic BLE → gamepad (no features)
3. **+1hr**: Add duplicate filtering
4. **+1.5hr**: Add gamepad batching (CRITICAL)
5. **+2hr**: Test & measure latency
6. **+2.5hr**: Add sprint/roll logic only if latency good
7. **+3hr**: Game testing
8. **DONE**: Ship it!

## Critical Implementation Notes

### DO:
- ✅ Process EVERY orientation update (don't drop data)
- ✅ Batch gamepad.update() calls (huge win)
- ✅ Filter duplicate moves (cube sends doubles)
- ✅ Use async/await for timing delays
- ✅ Measure actual cube frequency first

### DON'T:
- ❌ Block event loop with time.sleep()
- ❌ Call gamepad.update() after every change
- ❌ Coalesce/drop orientation updates
- ❌ Add features before core latency is good
- ❌ Assume <10ms is possible (physics says no)

## Measurement Script

Run `measure_cube_frequency.py` first to understand your cube's actual data rate. This will show:
- Actual orientation frequency (expect 15-20Hz)
- Move event patterns and duplicates
- Realistic latency targets for your specific cube
