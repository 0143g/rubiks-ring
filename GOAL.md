**PROJECT OUTLINE: GAN Cube → Elden Ring Controller**

## Current State
- ✅ GAN356 i3 cube connected via afedotov's gan-web-bluetooth library in browser
- ✅ Library successfully decrypts cube data and detects moves + gyro
- ✅ Full typescript source code available in cloned repo
- ✅ Cube MAC address: AB:12:34:62:BC:15

## Goal
Create a node.js application that:
1. Connects to GAN cube using existing library
2. Maps cube rotations to keyboard inputs for Elden Ring
3. Uses gyro data for camera/mouse movement
4. Runs outside browser for minimal latency

## Architecture Plan
```
GAN Cube (bluetooth) → node.js app → keyboard/mouse simulation → Elden Ring
                      ↑
                gan-web-bluetooth lib
```

## Questions

### 1. Encryption/Connection Analysis
- Examine `src/gan-cube-encrypter.ts` - how does MAC→AES key derivation work?
- Check `src/gan-smart-cube.ts` - what's the connection flow for Gen2 protocol?
- Does the library work in node.js or only browsers? Any Web Bluetooth API dependencies?

### 2. Event System Deep Dive  
- What's the exact structure of move events from the observable stream?
- How is gyro/quaternion data formatted in the events?
- What's the latency/frequency of move detection vs gyro updates?

### 3. Node.js Compatibility
- Can we run this library in node.js with a bluetooth adapter (like @abandonware/noble)?
- Any browser-specific APIs that need replacement?
- Dependencies needed for node.js bluetooth access?

### 4. Control Mapping Strategy
- What's the optimal move notation to game action mapping?
- How to implement smooth mouse movement from gyro quaternions?
- Best library for keyboard simulation (robotjs vs alternatives)?

### 5. Implementation Details
- Sample code structure for the game controller
- How to handle connection persistence and reconnection
- Performance optimization for gaming latency

## Deliverables
1. Analysis of encryption/connection mechanisms
2. Node.js compatibility assessment  
3. Event structure documentation
4. Complete game controller implementation
5. Setup/installation instructions

## Success Criteria
- Cube rotations trigger immediate keyboard presses in Elden Ring
- Gyro movement translates to smooth camera control
- <50ms latency from cube movement to game input
- Stable connection without dropouts
