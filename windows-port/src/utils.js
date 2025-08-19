/** Get current timestamp in milliseconds */
function now() {
  return Date.now();
}

/** Convert CP/CO/EP/EO arrays to Kociemba facelet string representation */
function toKociembaFacelets(cp, co, ep, eo) {
  // Validate input arrays
  if (!cp || !co || !ep || !eo) {
    console.error('[Utils] toKociembaFacelets: Invalid input arrays', { cp, co, ep, eo });
    return 'X'.repeat(54); // Return default state if invalid
  }
  
  if (cp.length !== 8 || co.length !== 8 || ep.length !== 12 || eo.length !== 12) {
    console.error('[Utils] toKociembaFacelets: Invalid array lengths', { 
      cpLen: cp?.length, coLen: co?.length, epLen: ep?.length, eoLen: eo?.length 
    });
    return 'X'.repeat(54); // Return default state if invalid
  }

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
    
    // Validate corner piece and orientation values
    if (piece < 0 || piece >= 8 || orientation < 0 || orientation > 2) {
      console.warn('[Utils] Invalid corner piece/orientation', { i, piece, orientation });
      continue; // Skip invalid corner
    }
    
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
    
    // Validate edge piece and orientation values
    if (piece < 0 || piece >= 12 || orientation < 0 || orientation > 1) {
      console.warn('[Utils] Invalid edge piece/orientation', { i, piece, orientation });
      continue; // Skip invalid edge
    }
    
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
function cubeTimestampLinearFit(dataPoints) {
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
 * Spherical Linear Interpolation (SLERP) between two quaternions
 * Provides smooth rotation interpolation for cube orientation
 */
function slerpQuaternions(q1, q2, t) {
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
function normalizeQuaternion(q) {
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
function quaternionAngularDistance(q1, q2) {
  const dot = Math.abs(q1.x * q2.x + q1.y * q2.y + q1.z * q2.z + q1.w * q2.w);
  return 2 * Math.acos(Math.min(1.0, dot));
}

/**
 * Smooth orientation data using a rolling average with SLERP
 */
function smoothOrientationData(orientations, windowSize = 3) {
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

/**
 * Standard face quaternions for cube orientation reference
 * All measurements taken with cube flat on desk
 */
const FACE_QUATERNIONS = {
  white_top_green_front: { x: -0.008, y: -0.011, z: 0.390, w: 0.921 },
  yellow_top_green_front: { x: -0.397, y: 0.918, z: -0.012, w: -0.002 },
  blue_top_white_front: { x: 0.662, y: 0.280, z: 0.275, w: 0.639 },
  green_top_white_front: { x: 0.286, y: -0.661, z: 0.644, w: -0.260 },
  red_top_white_front: { x: 0.666, y: -0.273, z: 0.645, w: 0.259 },
  orange_top_white_front: { x: 0.257, y: 0.673, z: -0.265, w: 0.642 }
};

/**
 * Multiply two quaternions (Hamilton product)
 */
function multiplyQuaternions(q1, q2) {
  return {
    x: q1.w * q2.x + q1.x * q2.w + q1.y * q2.z - q1.z * q2.y,
    y: q1.w * q2.y - q1.x * q2.z + q1.y * q2.w + q1.z * q2.x,
    z: q1.w * q2.z + q1.x * q2.y - q1.y * q2.x + q1.z * q2.w,
    w: q1.w * q2.w - q1.x * q2.x - q1.y * q2.y - q1.z * q2.z
  };
}

/**
 * Compute inverse/conjugate of a quaternion
 */
function inverseQuaternion(q) {
  const lengthSq = q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w;
  if (lengthSq === 0) {
    return { x: 0, y: 0, z: 0, w: 1 };
  }
  return {
    x: -q.x / lengthSq,
    y: -q.y / lengthSq,
    z: -q.z / lengthSq,
    w: q.w / lengthSq
  };
}

/**
 * CubeOrientationTransform handles coordinate system transformations
 * The GAN cube's internal axes are:
 * - X-axis: points toward RED face
 * - Y-axis: points toward WHITE face (top in standard position)
 * - Z-axis: points toward GREEN face (front in standard position)
 * 
 * The cube's factory default (0,0,0,-1) is impractical, so we use
 * "white top, green front" as our effective identity orientation.
 */
class CubeOrientationTransform {
  constructor() {
    // The quaternion for our chosen "home" position (white top, green front)
    this.HOME_QUATERNION = { x: -0.008, y: -0.011, z: 0.390, w: 0.921 };
    this.HOME_QUATERNION_INVERSE = inverseQuaternion(this.HOME_QUATERNION);
  }

  /**
   * Convert raw cube quaternion to normalized orientation
   * where (0,0,0,1) means white top, green front
   */
  normalizeOrientation(rawQuat) {
    // Multiply by inverse of home quaternion to get relative rotation
    return multiplyQuaternions(rawQuat, this.HOME_QUATERNION_INVERSE);
  }

  /**
   * Convert normalized orientation back to raw cube quaternion
   */
  denormalizeOrientation(normalizedQuat) {
    // Multiply by home quaternion to get raw rotation
    return multiplyQuaternions(normalizedQuat, this.HOME_QUATERNION);
  }

  /**
   * Get reference quaternions for standard cube positions
   */
  getFaceQuaternions() {
    return FACE_QUATERNIONS;
  }

  /**
   * Check if cube is near factory default orientation
   */
  isFactoryDefault(quat) {
    return Math.abs(quat.w + 1) < 0.1; // w ≈ -1
  }

  /**
   * Filter out sensor noise from quaternion values
   */
  filterNoise(quat, threshold = 0.02) {
    return {
      x: Math.abs(quat.x) < threshold ? 0 : quat.x,
      y: Math.abs(quat.y) < threshold ? 0 : quat.y,
      z: Math.abs(quat.z) < threshold ? 0 : quat.z,
      w: quat.w
    };
  }
}

module.exports = {
  now,
  toKociembaFacelets,
  cubeTimestampLinearFit,
  slerpQuaternions,
  normalizeQuaternion,
  quaternionAngularDistance,
  smoothOrientationData,
  multiplyQuaternions,
  inverseQuaternion,
  CubeOrientationTransform,
  FACE_QUATERNIONS
};