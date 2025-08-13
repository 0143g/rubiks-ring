# Global Orientation State Reference Document

## Project Overview

This project involves integrating a GAN Smart Cube (physical Rubik's cube with Bluetooth connectivity) with:
1. **Physical Cube**: A real GAN Smart Cube that transmits orientation data via Bluetooth
2. **Web Visualization**: A browser-based 3D visualization of the cube's state
3. **Virtual Xbox Controller**: A virtual controller interface for cube manipulation
4. **Bluetooth Communication Layer**: TypeScript library handling cube connectivity and data streams

The system receives quaternion orientation data from the physical cube and needs to consistently represent this orientation across all interfaces.

## Current State & Problem

### The Core Issue
We have three different orientation reference frames that are misaligned:

1. **Physical Cube's Internal Reference Frame**
   - Sends quaternion data (x, y, z, w) via Bluetooth
   - Has its own internal coordinate system defined by the hardware

2. **Visualization Reference Frame**  
   - Shows GREEN as front face on initial connection
   - May have different axis conventions (Y-up vs Z-up, left-handed vs right-handed)

3. **Virtual Xbox Controller Reference Frame**
   - Likely expects different orientation conventions
   - May map axes differently for intuitive control

### Observed Behavior

**Initial State (cube at rest, user perspective):**
- User sees: White top, Green front-left, Red front-right (isometric view)
- Quaternion: (-0.011, -0.011, 0.012, 1.000) ≈ identity rotation
- Visualization shows: GREEN as front face

**After "forward" rotation (Green on top):**
- Physical: Green top, White back, Yellow front
- Quaternion: (-0.721, -0.026, 0.007, 0.692) ≈ 90° rotation around X-axis
- Visualization state: [UNKNOWN - needs verification]
- Controller state: [UNKNOWN - needs verification]

**After additional "left" rotation:**
- Physical: Red top, Yellow front, Blue right, Green left  
- Quaternion: (-0.509, -0.509, -0.488, 0.494) ≈ compound rotation
- Visualization state: [UNKNOWN - needs verification]
- Controller state: [UNKNOWN - needs verification]

## Proposed Solution: Single Global Reference Frame

### Step 1: Define the Global Reference Frame

We need to establish ONE canonical reference frame for the entire system:

```
GLOBAL REFERENCE FRAME (Proposed):
- Origin: Center of cube
- X-axis: Points RIGHT (toward Red face in home position)
- Y-axis: Points UP (toward White face in home position)  
- Z-axis: Points FORWARD (toward Green face in home position)
- Coordinate System: Right-handed
- Home Position: White top, Green front (standard Rubik's cube orientation)
```

### Step 2: Create Transformation Matrices

For each system, we need a transformation matrix to convert TO and FROM the global frame:

1. **CubeToGlobal Transform**
   - Maps cube's internal quaternion to global reference frame
   - Likely needs axis remapping and/or rotation offset

2. **GlobalToVisualization Transform**
   - Maps global orientation to visualization's expected format
   - May need axis swapping if visualization uses different conventions

3. **GlobalToController Transform**
   - Maps global orientation to Xbox controller's expected input
   - May need different axis mappings for intuitive control

### Step 3: Implementation Strategy

```typescript
interface GlobalOrientation {
  quaternion: { x: number, y: number, z: number, w: number };
  euler?: { x: number, y: number, z: number }; // optional, for debugging
}

class OrientationManager {
  // Calibration offsets (to be determined)
  private cubeToGlobalOffset: Quaternion;
  private visualizationAxisMap: AxisMapping;
  private controllerAxisMap: AxisMapping;
  
  // Convert from cube's raw quaternion to global reference
  cubeToGlobal(cubeQuat: Quaternion): GlobalOrientation { }
  
  // Convert from global to visualization format
  globalToVisualization(global: GlobalOrientation): VisualizationOrientation { }
  
  // Convert from global to controller format
  globalToController(global: GlobalOrientation): ControllerOrientation { }
}
```

## Critical Questions for the Engineering Team

### 1. Cube Hardware Questions
- **Q1.1**: What is the exact coordinate system of the GAN Smart Cube? Is it documented anywhere?
- **Q1.2**: When the cube reports quaternion (0, 0, 0, 1), what is the physical orientation?
- **Q1.3**: Are the quaternion values consistent across different GAN cube models?

### 2. Visualization Questions
- **Q2.1**: What 3D library/framework is the visualization using? (Three.js, Babylon.js, etc.)
- **Q2.2**: What coordinate system does it use? (Y-up or Z-up, left or right-handed)
- **Q2.3**: How is the cube model oriented in the 3D scene file?
- **Q2.4**: Can we access/modify the visualization's camera position and orientation?

### 3. Xbox Controller Questions
- **Q3.1**: What does the virtual Xbox controller control? Camera? Cube rotation? Both?
- **Q3.2**: What input format does it expect? (Euler angles, quaternions, axis angles?)
- **Q3.3**: Are there any existing mappings we need to preserve for user experience?

### 4. Current Implementation Questions
- **Q4.1**: Is there existing calibration or offset code anywhere in the codebase?
- **Q4.2**: Are there any hardcoded rotation corrections being applied?
- **Q4.3**: Where exactly is the quaternion data being processed? (Multiple places?)

### 5. Testing & Validation Questions
- **Q5.1**: Do we have a test suite for orientation accuracy?
- **Q5.2**: Can we log raw quaternion data alongside visualization state for debugging?
- **Q5.3**: Is there a way to manually set orientations for testing the pipeline?

## Next Steps

1. **Gather Data**: Record quaternion values for all 24 possible cube orientations
2. **Analyze Mappings**: Determine the exact transformation needed from cube to global
3. **Implement Transform**: Create the OrientationManager class with proper transforms
4. **Test & Calibrate**: Verify consistency across all three systems
5. **Document**: Create clear documentation of the global reference frame

## Calibration Procedure (Proposed)

1. Place cube in known "home" position (White top, Green front)
2. Record quaternion value - this is our calibration reference
3. Rotate to each face orientation, recording quaternions
4. Calculate transformation matrix that maps recorded values to expected global values
5. Apply inverse transform to get consistent global state

## Success Criteria

- [ ] Cube in any physical orientation produces correct visualization
- [ ] Xbox controller inputs match visual expectations
- [ ] Rotating physical cube updates both visualization and controller state consistently
- [ ] No drift or accumulation of errors over time
- [ ] Clear documentation of coordinate systems and transformations

## Additional Considerations

- **Performance**: Quaternion operations should be optimized for real-time updates
- **Precision**: Use appropriate epsilon values for quaternion comparisons
- **Gimbal Lock**: Quaternions avoid this, but Euler conversions need care
- **User Calibration**: Consider adding a "reset orientation" button for users

---

*This document serves as the central reference for achieving consistent orientation state across all systems in the Rubik's cube project.*