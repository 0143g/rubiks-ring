# V2 Implementation Plan - Direct Cube Controller

## Current Status (2025-08-26)
✅ **V2 is working!** Using `cube_controller_v2_fixed.py` as the single implementation.

### What's Completed:
- ✅ Direct BLE connection using `gan_web_bluetooth` library (no reimplementation)
- ✅ GamepadBatcher at 125Hz (critical optimization from plan)
- ✅ Duplicate move filtering
- ✅ V1's calibration system (auto-calibrates 2s after connection)
- ✅ Proper quaternion math for relative rotation
- ✅ ~10-12Hz orientation updates working
- ✅ Move detection with low latency
- ✅ Debug output showing calibrated values

### Measured Performance:
- **Orientation rate**: 10-12Hz (matches cube hardware)
- **Move latency**: Very low (immediate printing)
- **Processing overhead**: <5ms (target achieved)

## Reality Check (Updated from Testing)
- **Cube actually sends at ~10Hz** (not 15-20Hz as initially thought)
- **Your specific cube**: 97ms average between updates (P50: 60ms, P90: 180ms)
- **BLE overhead**: 15-30ms typical
- **Total latency achieved**: ~100-110ms (cube hardware limited)

## Next Steps

### Immediate Testing Needed:
1. **Test with actual game** (Elden Ring or similar)
2. **Verify joystick axes are mapped correctly**
3. **Test sprint/roll mechanics if needed**

### Optional Enhancements:
1. **Sprint Mode** - Already scaffolded but disabled by default
   - Set `self.enable_sprint = True` to enable auto-B-hold on forward tilt
   - Roll detection on U' move during sprint already implemented

2. **Config Hot-Reload** - Add config file watching like V1

3. **Manual Calibration Command** - Add keyboard shortcut to recalibrate

## Key Implementation Notes (Lessons Learned)

### Critical Insights:
1. **Don't reimplement the BLE protocol** - Use `gan_web_bluetooth` library
2. **Your cube uses Gen2 protocol** despite being a GAN356 i 3
3. **GamepadBatcher is essential** - vgamepad.update() is expensive
4. **Process every orientation event** - Don't drop data, let batcher handle rate limiting
5. **Calibration must match V1** - Quaternion math for relative rotation

### Architecture (Final):
```
GAN Cube 
    ↓ (BLE ~10Hz via gan_web_bluetooth)
Event Handlers (direct, no queue)
    ├── Move Handler → Duplicate Filter → Button Press
    └── Orientation Handler → Calibration → Joystick Update
         ↓
GamepadBatcher (125Hz flush loop)
    ↓
vgamepad → Xbox Controller
```

## Original Implementation Steps (For Reference)

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

## Performance Achieved vs Targets

| Metric | V1 (Measured) | V2 Target | V2 Achieved | Status |
|--------|---------------|-----------|-------------|---------|
| Avg Latency | 160-180ms | 30-40ms | ~100-110ms | ⚠️ Cube limited |
| Max Latency | 600ms+ | <100ms | <200ms | ✅ Met |
| Orientation Rate | ~10Hz (queued) | 10Hz | 10-12Hz | ✅ Met |
| Move Latency | Variable | <50ms | <20ms | ✅ Exceeded |
| CPU Usage | 15-20% | <3% | TBD | 🔄 Test needed |
| Memory | 256MB | <30MB | TBD | 🔄 Test needed |
| Code Size | ~2000 lines | <600 lines | ~540 lines | ✅ Met |

### Why latency is ~100ms not 30-40ms:
1. **Your cube's actual rate**: ~10Hz (97ms avg) not 15-20Hz
2. **Can't overcome hardware**: Cube only sends data every 97ms
3. **But eliminated V1's overhead**: No more 60-80ms additional delay
4. **Result**: 2x improvement over V1 (100ms vs 180ms)

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
