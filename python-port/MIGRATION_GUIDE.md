# TypeScript to Python Migration Guide for gan-web-bluetooth

## Overview
This guide provides a comprehensive roadmap for porting the gan-web-bluetooth TypeScript library to Python, maintaining functionality while adapting to Python's ecosystem and idioms.

## Source Structure Analysis

### TypeScript Files (8 files total)
1. **index.ts** - Main export module (6 lines)
2. **gan-smart-timer.ts** - Timer functionality 
3. **gan-smart-cube.ts** - Cube connection and protocol detection
4. **gan-cube-protocol.ts** - Protocol implementations (Gen2/3/4)
5. **gan-cube-encrypter.ts** - AES encryption for different generations
6. **gan-cube-definitions.ts** - Constants, UUIDs, encryption keys
7. **utils.ts** - Utilities for timestamps, quaternions, Kociemba conversion
8. **utils_backup.ts** - Backup utilities file

### Core Dependencies
- **aes-js** - AES encryption
- **rxjs** - Reactive programming with Observables
- **@types/web-bluetooth** - Web Bluetooth API types

## Python Package Structure

```
python-port/
├── gan_web_bluetooth/
│   ├── __init__.py              # Main exports
│   ├── smart_timer.py           # GAN Smart Timer implementation
│   ├── smart_cube.py            # GAN Smart Cube implementation
│   ├── protocols/
│   │   ├── __init__.py
│   │   ├── base.py              # Base protocol interface
│   │   ├── gen2.py              # Gen2 protocol implementation
│   │   ├── gen3.py              # Gen3 protocol implementation
│   │   └── gen4.py              # Gen4 protocol implementation
│   ├── encryption/
│   │   ├── __init__.py
│   │   └── encrypters.py        # AES encrypters for each generation
│   ├── definitions.py           # Constants, UUIDs, keys
│   ├── utils.py                 # Utilities (timestamps, quaternions, etc.)
│   └── types.py                 # Type definitions
├── examples/
│   ├── timer_example.py
│   ├── cube_example.py
│   └── controller_bridge.py
├── tests/
│   ├── test_encryption.py
│   ├── test_protocols.py
│   ├── test_utils.py
│   └── test_integration.py
├── requirements.txt
├── setup.py
├── README.md
└── LICENSE

```

## Library Mapping: TypeScript/JS → Python

### Core Libraries

| TypeScript/JavaScript | Python Equivalent | Purpose |
|-----------------------|-------------------|---------|
| Web Bluetooth API | `bleak` | Cross-platform BLE library |
| rxjs (Observables) | `asyncio` + custom EventEmitter | Async event handling |
| aes-js | `cryptography` or `pycryptodome` | AES encryption |
| TypeScript types | `typing` + `dataclasses` | Type hints and data structures |
| Uint8Array | `bytes` / `bytearray` | Binary data handling |
| ArrayBuffer | `memoryview` / `bytes` | Binary buffers |

### Specific Replacements

1. **Bluetooth Communication**
   - TypeScript: `navigator.bluetooth.*`
   - Python: `bleak.BleakClient`, `bleak.BleakScanner`

2. **Reactive Programming**
   - TypeScript: `Observable`, `Subject` from rxjs
   - Python: Custom EventEmitter class using `asyncio.Queue` or `pyee` library

3. **AES Encryption**
   - TypeScript: `aes-js` ModeOfOperation.ecb
   - Python: `cryptography.hazmat.primitives.ciphers` or `Crypto.Cipher.AES`

4. **Type System**
   - TypeScript: interfaces, types, enums
   - Python: `TypedDict`, `dataclass`, `Enum`, `Protocol`

## Key Architectural Changes

### 1. Async/Await Pattern
**TypeScript:**
```typescript
async connectCube(): Promise<void> {
    const device = await navigator.bluetooth.requestDevice({...});
    const server = await device.gatt.connect();
}
```

**Python:**
```python
async def connect_cube(self) -> None:
    device = await BleakScanner.find_device_by_filter(...)
    async with BleakClient(device) as client:
        await client.connect()
```

### 2. Observable Pattern → Event Emitter
**TypeScript:**
```typescript
moveEvent$ = new Subject<MoveEvent>();
moveEvent$.subscribe(event => console.log(event));
```

**Python:**
```python
class CubeEventEmitter:
    def __init__(self):
        self._handlers = defaultdict(list)
    
    def on(self, event: str, handler: Callable):
        self._handlers[event].append(handler)
    
    def emit(self, event: str, data: Any):
        for handler in self._handlers[event]:
            asyncio.create_task(handler(data))
```

### 3. Binary Data Handling
**TypeScript:**
```typescript
const data = new Uint8Array([0x01, 0x02, 0x03]);
const view = new DataView(buffer);
const value = view.getUint16(0, true); // little-endian
```

**Python:**
```python
import struct

data = bytes([0x01, 0x02, 0x03])
value = struct.unpack('<H', data[0:2])[0]  # little-endian uint16
```

### 4. MAC Address Handling
**TypeScript:** Extract from manufacturer data in advertisement
**Python:** Use `bleak` advertisement data or device properties

### 5. Class Structure
**TypeScript:** Class with private fields and methods
**Python:** Class with convention-based privacy (`_` prefix)

## Implementation Roadmap

### Phase 1: Core Infrastructure (Week 1)
- [ ] Set up Python package structure
- [ ] Implement type definitions (`types.py`)
- [ ] Port constants and definitions (`definitions.py`)
- [ ] Create base Bluetooth abstraction using `bleak`

### Phase 2: Utilities and Encryption (Week 1-2)
- [ ] Port utility functions (`utils.py`)
  - [ ] Timestamp functions
  - [ ] Quaternion operations
  - [ ] Linear regression for clock sync
  - [ ] Kociemba facelet conversion
- [ ] Implement AES encrypters for Gen2/3/4

### Phase 3: Protocol Implementation (Week 2-3)
- [ ] Create base protocol interface
- [ ] Implement Gen2 protocol
- [ ] Implement Gen3 protocol
- [ ] Implement Gen4 protocol
- [ ] Add protocol auto-detection

### Phase 4: Device Classes (Week 3-4)
- [ ] Implement GanSmartTimer class
- [ ] Implement GanSmartCube class
- [ ] Add event emitter system
- [ ] Implement device discovery and connection

### Phase 5: Testing and Examples (Week 4)
- [ ] Unit tests for encryption
- [ ] Unit tests for protocols
- [ ] Integration tests with mock BLE
- [ ] Create usage examples
- [ ] Port controller bridge functionality

### Phase 6: Documentation and Polish (Week 5)
- [ ] API documentation
- [ ] Usage guide
- [ ] Performance optimization
- [ ] Cross-platform testing (Windows, Linux, macOS)

## Critical Implementation Notes

### 1. Bluetooth Permissions
- Python doesn't have browser-style permission prompts
- May require system-level Bluetooth permissions on some platforms
- Consider adding permission checking utilities

### 2. Platform Differences
- `bleak` handles cross-platform differences internally
- Test on Windows, Linux, macOS for compatibility
- May need platform-specific code for advanced features

### 3. Performance Considerations
- Python may have higher latency than browser Web Bluetooth
- Consider using `numpy` for quaternion math if performance critical
- Profile and optimize hot paths (encryption, event processing)

### 4. Threading vs Async
- Use `asyncio` throughout for consistency with `bleak`
- Avoid mixing threading and async patterns
- Consider `trio` or `anyio` for structured concurrency

### 5. Error Handling
- Python exceptions instead of Promise rejections
- Implement proper cleanup in context managers
- Add retry logic for Bluetooth connection issues

## Dependencies (requirements.txt)

```
bleak>=0.21.0           # Bluetooth Low Energy
cryptography>=41.0.0    # AES encryption
numpy>=1.24.0          # Numerical operations (optional, for performance)
pyee>=11.0.0           # Event emitter (optional)
typing-extensions>=4.7.0  # Backported typing features
dataclasses>=0.6       # For Python < 3.7
asyncio>=3.4.3         # Async support
```

## Testing Strategy

### Unit Tests
- Test encryption/decryption for each generation
- Test protocol command encoding/decoding
- Test utility functions (quaternions, timestamps, etc.)
- Mock Bluetooth for protocol tests

### Integration Tests
- Test with real GAN devices if available
- Test connection/disconnection cycles
- Test event emission and handling
- Test error recovery scenarios

### Performance Tests
- Measure latency from cube move to event emission
- Profile CPU usage during active connection
- Test with multiple simultaneous connections
- Benchmark encryption performance

## Migration Validation Checklist

- [ ] All TypeScript classes have Python equivalents
- [ ] All public APIs are exposed with similar interfaces
- [ ] Encryption produces identical output to TypeScript version
- [ ] Protocol messages match byte-for-byte
- [ ] Event system provides similar subscription model
- [ ] Examples demonstrate feature parity
- [ ] Documentation covers all public APIs
- [ ] Tests achieve >80% code coverage

## Common Pitfalls to Avoid

1. **Don't assume Web Bluetooth behavior** - `bleak` works differently
2. **Handle cleanup properly** - Use context managers for connections
3. **Test endianness carefully** - Ensure binary data parsing matches
4. **Validate encryption** - Test against known inputs/outputs from TS version
5. **Consider battery usage** - Python may use more power than browser
6. **Plan for distribution** - Consider PyPI packaging from the start

## Next Steps

1. Review this guide and adjust based on project requirements
2. Set up development environment with Python 3.8+
3. Install initial dependencies (`pip install bleak cryptography`)
4. Begin with Phase 1: Core Infrastructure
5. Create initial tests alongside implementation
6. Iterate based on testing with actual GAN devices