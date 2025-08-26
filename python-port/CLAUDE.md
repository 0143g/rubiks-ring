# GAN Cube Gamepad Controller - Project Analysis & V2 Plan

## Project Overview
This project enables control of PC games using a GAN356 i 3 Rubik's cube as an input device. The cube connects via Bluetooth, sends gyroscopic and face turn data, which is translated into gamepad inputs. Currently experiencing significant input lag and "traffic jam" issues where inputs get delayed by several seconds.

## Current Architecture

### Core Components
1. **cube_dashboard.py** - Flask/SocketIO web dashboard
   - Manages Bluetooth connection to cube via `gan_web_bluetooth` library
   - Processes cube events (moves, orientation, battery)
   - Forwards data to controller bridge via WebSocket
   - Uses threading with asyncio event loops

2. **controller_bridge.py** - Virtual gamepad controller
   - WebSocket server receiving cube data from dashboard
   - Translates cube moves to Xbox controller inputs via `vgamepad`
   - Manages sprint mode, roll combos, and button mappings
   - Windows-only due to vgamepad dependency

3. **gan_web_bluetooth/** - Bluetooth communication library
   - Handles BLE connection using `bleak`
   - Implements GAN cube protocols (Gen2/3/4)
   - Manages encryption and data parsing
   - Event-based architecture

### Data Flow
```
GAN Cube → [Bluetooth] → cube_dashboard → [WebSocket] → controller_bridge → [vgamepad] → Game
```

## Performance Issues Identified

### 1. Multi-Layer Async Architecture
- **Problem**: Complex async/threading hybrid causing event queue buildup
- **Evidence**: LATENCY.txt shows delays up to 600ms, averaging 60-80ms
- **Location**: cube_dashboard.py uses both threading and asyncio, creating synchronization overhead

### 2. Event Queue Bottlenecks
- **Problem**: Events queued in multiple places causing cascading delays
- **Evidence**: diagnostic_logger shows queue buildups >100 items
- **Location**: 
  - cube_dashboard.py:267 - `event_queue = asyncio.Queue(maxsize=1000)`
  - _process_event_queue() processes events serially

### 3. Excessive Inter-Process Communication
- **Problem**: Dashboard → Bridge WebSocket adds unnecessary latency
- **Evidence**: Each message goes through JSON serialization/deserialization
- **Location**: Two separate Python processes communicating over localhost WebSocket

### 4. Rate Limiting Conflicts
- **Problem**: Multiple rate limiters fighting each other
- **Evidence**: 
  - Dashboard: 16ms rate limit (cube_dashboard.py:67)
  - Bridge: 1ms rate limit (controller_bridge.py:34)
  - Conflicting timers cause input bunching

### 5. Synchronous Blocking Operations
- **Problem**: Gamepad updates block event processing
- **Evidence**: ThreadPoolExecutor with single worker (controller_bridge.py:136)
- **Location**: vgamepad operations not truly async

## V2 Architecture Proposal

### Design Principles
1. **Single Process**: Eliminate WebSocket IPC overhead
2. **Pure Async**: Remove threading/asyncio hybrid complexity
3. **Direct Pipeline**: Bluetooth → Processing → Gamepad with minimal buffering
4. **Zero-Copy**: Process data in-place without serialization
5. **Backpressure**: Drop old events when new ones arrive

### Proposed Structure

```
v2_controller.py (Single File Solution)
├── BleakClient (Direct Bluetooth)
├── Event Processing (Pure async)
├── State Machine (Lockless)
└── Gamepad Output (Non-blocking)
```

### Key Improvements

#### 1. Direct Bluetooth Integration
```python
class CubeController:
    async def __init__(self):
        self.client = BleakClient(address)
        self.gamepad = vg.VX360Gamepad()
        # No intermediate servers or queues
```

#### 2. Lockless State Management
```python
# Use atomic operations and ring buffers
class StateManager:
    def __init__(self):
        self.orientation = AtomicReference()
        self.move_buffer = RingBuffer(size=10)  # Only keep latest moves
```

#### 3. Event Coalescing
```python
# Combine multiple orientation updates into single gamepad update
async def process_orientation_batch(self, events):
    latest = events[-1]  # Only process most recent
    await self.update_gamepad_direct(latest)
```

#### 4. Non-Blocking Gamepad Updates
```python
# Fire-and-forget gamepad updates
def update_gamepad_nowait(self, data):
    # Update gamepad state without await
    self.gamepad.left_joystick(x, y)
    self.gamepad.update()
    # No await, no blocking
```

#### 5. Adaptive Rate Control
```python
# Dynamic rate limiting based on input frequency
class AdaptiveRateLimiter:
    def should_process(self, event_type):
        if self.is_falling_behind():
            return event_type == 'move'  # Prioritize moves over orientation
        return True
```

## Implementation Plan

### Phase 1: Proof of Concept (Week 1)
- [ ] Create v2_controller.py with direct Bluetooth connection
- [ ] Implement basic move → button mapping
- [ ] Test latency improvement

### Phase 2: Core Features (Week 2)
- [ ] Port orientation processing
- [ ] Implement state coalescing
- [ ] Add configuration support

### Phase 3: Optimization (Week 3)
- [ ] Profile and eliminate remaining bottlenecks
- [ ] Add adaptive rate limiting
- [ ] Implement telemetry for monitoring

### Phase 4: Polish (Week 4)
- [ ] Error handling and reconnection logic
- [ ] GUI for configuration (optional)
- [ ] Documentation and testing

## Expected Performance Gains

| Metric | Current | Target V2 | Improvement |
|--------|---------|-----------|-------------|
| Average Latency | 60-80ms | <10ms | 6-8x |
| Max Latency | 600ms | <50ms | 12x |
| Input Rate | 60-125 FPS | 250+ FPS | 2-4x |
| CPU Usage | 15-20% | <5% | 3-4x |
| Memory Usage | 256MB | <50MB | 5x |

## Migration Strategy

1. **Parallel Development**: Build V2 alongside V1
2. **Feature Parity**: Ensure all mappings work
3. **A/B Testing**: Compare latency metrics
4. **Gradual Rollout**: Test with different games
5. **Fallback Option**: Keep V1 for compatibility

## Technical Requirements

### Dependencies to Keep
- `bleak` - Bluetooth LE communication
- `vgamepad` - Virtual gamepad (Windows)
- `pycryptodome` - Encryption for cube protocol

### Dependencies to Remove
- `flask` & `flask-socketio` - No web dashboard needed
- `websockets` - No IPC required
- `psutil` - Diagnostic overhead

### New Dependencies
- `uvloop` (optional) - Faster event loop
- `numpy` (optional) - Efficient array operations

## Risk Mitigation

1. **Bluetooth Stability**: Implement exponential backoff reconnection
2. **Game Compatibility**: Test with multiple games early
3. **Platform Support**: Consider Linux/Mac gamepad alternatives
4. **Cube Variations**: Maintain protocol compatibility

## Success Criteria

- [ ] Sub-10ms average latency
- [ ] Zero input drops during normal use  
- [ ] Stable 8-hour gaming sessions
- [ ] <5% CPU usage
- [ ] Clean, maintainable codebase

## Next Steps

1. Review and approve this plan
2. Set up V2 development branch
3. Begin Phase 1 implementation
4. Create benchmarking suite for A/B testing
5. Document V2 API for future enhancements
