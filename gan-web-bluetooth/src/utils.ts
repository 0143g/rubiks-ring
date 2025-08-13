/** Get current timestamp in milliseconds */
function now(): number {
  return Date.now();
}

/** Convert CP/CO/EP/EO arrays to Kociemba facelet string representation */
function toKociembaFacelets(cp: number[], co: number[], ep: number[], eo: number[]): string {
  const facelets = new Array(54).fill('X');
  
  // Set center pieces (indices 4, 13, 22, 31, 40, 49 for URFDLB)
  const centers = [4, 13, 22, 31, 40, 49];
  const centerColors = 'URFDLB';
  centers.forEach((pos, i) => facelets[pos] = centerColors[i]);
  
  // Set corner pieces
  const cornerPositions = [
    [0, 9, 20], [2, 36, 11], [8, 18, 38], [6, 27, 29],  // Top corners
    [51, 35, 17], [53, 26, 44], [47, 15, 42], [45, 24, 33]  // Bottom corners
  ];
  
  const cornerColors = [
    ['U', 'R', 'F'], ['U', 'B', 'R'], ['U', 'L', 'B'], ['U', 'F', 'L'],
    ['D', 'F', 'R'], ['D', 'R', 'B'], ['D', 'B', 'L'], ['D', 'L', 'F']
  ];
  
  for (let i = 0; i < 8; i++) {
    const piece = cp[i];
    const orientation = co[i];
    const positions = cornerPositions[i];
    const colors = cornerColors[piece];
    
    for (let j = 0; j < 3; j++) {
      facelets[positions[j]] = colors[(j + orientation) % 3];
    }
  }
  
  // Set edge pieces
  const edgePositions = [
    [1, 37], [5, 10], [7, 19], [3, 28],  // Top edges
    [52, 16], [50, 43], [46, 25], [48, 34],  // Bottom edges
    [12, 21], [14, 23], [32, 41], [30, 39]   // Middle edges
  ];
  
  const edgeColors = [
    ['U', 'F'], ['U', 'R'], ['U', 'B'], ['U', 'L'],
    ['D', 'F'], ['D', 'R'], ['D', 'B'], ['D', 'L'],
    ['F', 'R'], ['F', 'L'], ['B', 'R'], ['B', 'L']
  ];
  
  for (let i = 0; i < 12; i++) {
    const piece = ep[i];
    const orientation = eo[i];
    const positions = edgePositions[i];
    const colors = edgeColors[piece];
    
    facelets[positions[0]] = colors[orientation];
    facelets[positions[1]] = colors[1 - orientation];
  }
  
  return facelets.join('');
}

/** 
 * Perform linear regression on cube timestamp vs host timestamp data points
 * to compensate for cube clock drift and synchronize timestamps
 */
function cubeTimestampLinearFit(dataPoints: Array<{cubeTime: number, hostTime: number}>): {slope: number, intercept: number} {
  if (dataPoints.length < 2) {
    return { slope: 1, intercept: 0 };
  }
  
  const n = dataPoints.length;
  let sumX = 0, sumY = 0, sumXY = 0, sumXX = 0;
  
  for (const point of dataPoints) {
    sumX += point.cubeTime;
    sumY += point.hostTime;
    sumXY += point.cubeTime * point.hostTime;
    sumXX += point.cubeTime * point.cubeTime;
  }
  
  const slope = (n * sumXY - sumX * sumY) / (n * sumXX - sumX * sumX);
  const intercept = (sumY - slope * sumX) / n;
  
  return { slope, intercept };
}

/** 
 * Quaternion type for orientation calculations
 */
type Quaternion = {
  x: number;
  y: number;
  z: number;
  w: number;
};

/**
 * Spherical Linear Interpolation (SLERP) between two quaternions
 * Provides smooth rotation interpolation for cube orientation
 */
function slerpQuaternions(q1: Quaternion, q2: Quaternion, t: number): Quaternion {
  // Clamp interpolation parameter
  t = Math.max(0, Math.min(1, t));
  
  // Calculate dot product
  let dot = q1.x * q2.x + q1.y * q2.y + q1.z * q2.z + q1.w * q2.w;
  
  // If dot product is negative, slerp won't take the shorter path
  // So negate one quaternion to correct this
  if (dot < 0.0) {
    q2 = { x: -q2.x, y: -q2.y, z: -q2.z, w: -q2.w };
    dot = -dot;
  }
  
  // If the inputs are too close for comfort, linearly interpolate
  if (dot > 0.9995) {
    const result = {
      x: q1.x + t * (q2.x - q1.x),
      y: q1.y + t * (q2.y - q1.y),
      z: q1.z + t * (q2.z - q1.z),
      w: q1.w + t * (q2.w - q1.w)
    };
    return normalizeQuaternion(result);
  }
  
  // Calculate the half angle between quaternions
  const theta0 = Math.acos(Math.abs(dot));
  const sinTheta0 = Math.sin(theta0);
  
  const theta = theta0 * t;
  const sinTheta = Math.sin(theta);
  
  const s0 = Math.cos(theta) - dot * sinTheta / sinTheta0;
  const s1 = sinTheta / sinTheta0;
  
  return {
    x: s0 * q1.x + s1 * q2.x,
    y: s0 * q1.y + s1 * q2.y,
    z: s0 * q1.z + s1 * q2.z,
    w: s0 * q1.w + s1 * q2.w
  };
}

/**
 * Normalize a quaternion to unit length
 */
function normalizeQuaternion(q: Quaternion): Quaternion {
  const length = Math.sqrt(q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w);
  if (length === 0) {
    return { x: 0, y: 0, z: 0, w: 1 };
  }
  return {
    x: q.x / length,
    y: q.y / length,
    z: q.z / length,
    w: q.w / length
  };
}

/**
 * Calculate angular distance between two quaternions in radians
 */
function quaternionAngularDistance(q1: Quaternion, q2: Quaternion): number {
  const dot = Math.abs(q1.x * q2.x + q1.y * q2.y + q1.z * q2.z + q1.w * q2.w);
  return 2 * Math.acos(Math.min(1.0, dot));
}

/**
 * Smooth orientation data using a rolling average with SLERP
 */
function smoothOrientationData(
  orientations: Array<{quaternion: Quaternion, timestamp: number}>, 
  windowSize: number = 3
): Quaternion | null {
  if (orientations.length < 2) return null;
  
  // Use most recent orientations within window
  const recent = orientations.slice(-windowSize);
  
  // Weight more recent samples higher
  let result = recent[0].quaternion;
  for (let i = 1; i < recent.length; i++) {
    const weight = i / (recent.length - 1);
    result = slerpQuaternions(result, recent[i].quaternion, weight);
  }
  
  return result;
}

export {
  now,
  toKociembaFacelets,
  cubeTimestampLinearFit,
  slerpQuaternions,
  normalizeQuaternion,
  quaternionAngularDistance,
  smoothOrientationData
};

export type { Quaternion };