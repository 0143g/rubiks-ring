"""Utility functions for GAN cube operations."""

import time
import math
from typing import List, Dict, Tuple, Optional, NamedTuple
from dataclasses import dataclass
import numpy as np


def now() -> float:
    """Get current timestamp in milliseconds."""
    return time.time() * 1000


def to_kociemba_facelets(cp: List[int], co: List[int], ep: List[int], eo: List[int]) -> str:
    """
    Convert CP/CO/EP/EO arrays to Kociemba facelet string representation.
    
    Args:
        cp: Corner permutation array
        co: Corner orientation array
        ep: Edge permutation array
        eo: Edge orientation array
    
    Returns:
        54-character string representing cube state in Kociemba format
    """
    facelets = ['X'] * 54
    
    # Set center pieces (indices 4, 13, 22, 31, 40, 49 for URFDLB)
    centers = [4, 13, 22, 31, 40, 49]
    center_colors = 'URFDLB'
    for pos, color in zip(centers, center_colors):
        facelets[pos] = color
    
    # Set corner pieces
    corner_positions = [
        [0, 9, 20], [2, 36, 11], [8, 18, 38], [6, 27, 29],  # Top corners
        [51, 35, 17], [53, 26, 44], [47, 15, 42], [45, 24, 33]  # Bottom corners
    ]
    
    corner_colors = [
        ['U', 'R', 'F'], ['U', 'B', 'R'], ['U', 'L', 'B'], ['U', 'F', 'L'],
        ['D', 'F', 'R'], ['D', 'R', 'B'], ['D', 'B', 'L'], ['D', 'L', 'F']
    ]
    
    for i in range(8):
        piece = cp[i]
        orientation = co[i]
        positions = corner_positions[i]
        colors = corner_colors[piece]
        
        for j in range(3):
            facelets[positions[j]] = colors[(j + orientation) % 3]
    
    # Set edge pieces
    edge_positions = [
        [1, 37], [5, 10], [7, 19], [3, 28],  # Top edges
        [52, 16], [50, 43], [46, 25], [48, 34],  # Bottom edges
        [12, 21], [14, 23], [32, 41], [30, 39]   # Middle edges
    ]
    
    edge_colors = [
        ['U', 'F'], ['U', 'R'], ['U', 'B'], ['U', 'L'],
        ['D', 'F'], ['D', 'R'], ['D', 'B'], ['D', 'L'],
        ['F', 'R'], ['F', 'L'], ['B', 'R'], ['B', 'L']
    ]
    
    for i in range(12):
        piece = ep[i]
        orientation = eo[i]
        positions = edge_positions[i]
        colors = edge_colors[piece]
        
        facelets[positions[0]] = colors[orientation]
        facelets[positions[1]] = colors[1 - orientation]
    
    return ''.join(facelets)


@dataclass
class LinearFitResult:
    """Result of linear regression fitting."""
    slope: float
    intercept: float


def cube_timestamp_linear_fit(data_points: List[Dict[str, float]]) -> LinearFitResult:
    """
    Perform linear regression on cube timestamp vs host timestamp data points
    to compensate for cube clock drift and synchronize timestamps.
    
    Args:
        data_points: List of dicts with 'cube_time' and 'host_time' keys
    
    Returns:
        LinearFitResult with slope and intercept
    """
    if len(data_points) < 2:
        return LinearFitResult(slope=1.0, intercept=0.0)
    
    n = len(data_points)
    sum_x = sum_y = sum_xy = sum_xx = 0.0
    
    for point in data_points:
        x = point['cube_time']
        y = point['host_time']
        sum_x += x
        sum_y += y
        sum_xy += x * y
        sum_xx += x * x
    
    denominator = n * sum_xx - sum_x * sum_x
    if abs(denominator) < 1e-10:  # Avoid division by zero
        return LinearFitResult(slope=1.0, intercept=0.0)
    
    slope = (n * sum_xy - sum_x * sum_y) / denominator
    intercept = (sum_y - slope * sum_x) / n
    
    return LinearFitResult(slope=slope, intercept=intercept)


@dataclass
class Quaternion:
    """Quaternion for orientation calculations."""
    x: float
    y: float
    z: float
    w: float
    
    def to_array(self) -> np.ndarray:
        """Convert to numpy array."""
        return np.array([self.x, self.y, self.z, self.w])
    
    @classmethod
    def from_array(cls, arr: np.ndarray) -> 'Quaternion':
        """Create from numpy array."""
        return cls(x=arr[0], y=arr[1], z=arr[2], w=arr[3])


def normalize_quaternion(q: Quaternion) -> Quaternion:
    """Normalize a quaternion to unit length."""
    length = math.sqrt(q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w)
    if length == 0:
        return Quaternion(x=0, y=0, z=0, w=1)
    return Quaternion(
        x=q.x / length,
        y=q.y / length,
        z=q.z / length,
        w=q.w / length
    )


def slerp_quaternions(q1: Quaternion, q2: Quaternion, t: float) -> Quaternion:
    """
    Spherical Linear Interpolation (SLERP) between two quaternions.
    Provides smooth rotation interpolation for cube orientation.
    
    Args:
        q1: Start quaternion
        q2: End quaternion
        t: Interpolation parameter (0 to 1)
    
    Returns:
        Interpolated quaternion
    """
    # Clamp interpolation parameter
    t = max(0, min(1, t))
    
    # Calculate dot product
    dot = q1.x * q2.x + q1.y * q2.y + q1.z * q2.z + q1.w * q2.w
    
    # If dot product is negative, negate one quaternion to take shorter path
    if dot < 0.0:
        q2 = Quaternion(x=-q2.x, y=-q2.y, z=-q2.z, w=-q2.w)
        dot = -dot
    
    # If inputs are too close, linearly interpolate
    if dot > 0.9995:
        result = Quaternion(
            x=q1.x + t * (q2.x - q1.x),
            y=q1.y + t * (q2.y - q1.y),
            z=q1.z + t * (q2.z - q1.z),
            w=q1.w + t * (q2.w - q1.w)
        )
        return normalize_quaternion(result)
    
    # Calculate the half angle between quaternions
    theta0 = math.acos(abs(dot))
    sin_theta0 = math.sin(theta0)
    
    theta = theta0 * t
    sin_theta = math.sin(theta)
    
    s0 = math.cos(theta) - dot * sin_theta / sin_theta0
    s1 = sin_theta / sin_theta0
    
    return Quaternion(
        x=s0 * q1.x + s1 * q2.x,
        y=s0 * q1.y + s1 * q2.y,
        z=s0 * q1.z + s1 * q2.z,
        w=s0 * q1.w + s1 * q2.w
    )


def quaternion_angular_distance(q1: Quaternion, q2: Quaternion) -> float:
    """
    Calculate angular distance between two quaternions in radians.
    
    Args:
        q1: First quaternion
        q2: Second quaternion
    
    Returns:
        Angular distance in radians
    """
    dot = abs(q1.x * q2.x + q1.y * q2.y + q1.z * q2.z + q1.w * q2.w)
    return 2 * math.acos(min(1.0, dot))


def smooth_orientation_data(
    orientations: List[Dict[str, any]], 
    window_size: int = 3
) -> Optional[Quaternion]:
    """
    Smooth orientation data using a rolling average with SLERP.
    
    Args:
        orientations: List of dicts with 'quaternion' and 'timestamp' keys
        window_size: Number of recent samples to average
    
    Returns:
        Smoothed quaternion or None if insufficient data
    """
    if len(orientations) < 2:
        return None
    
    # Use most recent orientations within window
    recent = orientations[-window_size:]
    
    # Weight more recent samples higher
    result = recent[0]['quaternion']
    for i in range(1, len(recent)):
        weight = i / (len(recent) - 1)
        result = slerp_quaternions(result, recent[i]['quaternion'], weight)
    
    return result


def multiply_quaternions(q1: Quaternion, q2: Quaternion) -> Quaternion:
    """
    Multiply two quaternions (Hamilton product).
    
    Args:
        q1: First quaternion
        q2: Second quaternion
    
    Returns:
        Product quaternion
    """
    return Quaternion(
        x=q1.w * q2.x + q1.x * q2.w + q1.y * q2.z - q1.z * q2.y,
        y=q1.w * q2.y - q1.x * q2.z + q1.y * q2.w + q1.z * q2.x,
        z=q1.w * q2.z + q1.x * q2.y - q1.y * q2.x + q1.z * q2.w,
        w=q1.w * q2.w - q1.x * q2.x - q1.y * q2.y - q1.z * q2.z
    )


def inverse_quaternion(q: Quaternion) -> Quaternion:
    """
    Compute inverse/conjugate of a quaternion.
    
    Args:
        q: Input quaternion
    
    Returns:
        Inverse quaternion
    """
    length_sq = q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w
    if length_sq == 0:
        return Quaternion(x=0, y=0, z=0, w=1)
    return Quaternion(
        x=-q.x / length_sq,
        y=-q.y / length_sq,
        z=-q.z / length_sq,
        w=q.w / length_sq
    )


# Standard face quaternions for cube orientation reference
FACE_QUATERNIONS = {
    'white_top_green_front': Quaternion(x=-0.008, y=-0.011, z=0.390, w=0.921),
    'yellow_top_green_front': Quaternion(x=-0.397, y=0.918, z=-0.012, w=-0.002),
    'blue_top_white_front': Quaternion(x=0.662, y=0.280, z=0.275, w=0.639),
    'green_top_white_front': Quaternion(x=0.286, y=-0.661, z=0.644, w=-0.260),
    'red_top_white_front': Quaternion(x=0.666, y=-0.273, z=0.645, w=0.259),
    'orange_top_white_front': Quaternion(x=0.257, y=0.673, z=-0.265, w=0.642)
}


class CubeOrientationTransform:
    """
    Handles coordinate system transformations for cube orientation.
    
    The GAN cube's internal axes are:
    - X-axis: points toward RED face
    - Y-axis: points toward WHITE face (top in standard position)
    - Z-axis: points toward GREEN face (front in standard position)
    
    The cube's factory default (0,0,0,-1) is impractical, so we use
    "white top, green front" as our effective identity orientation.
    """
    
    def __init__(self):
        # The quaternion for our chosen "home" position (white top, green front)
        self.HOME_QUATERNION = Quaternion(x=-0.008, y=-0.011, z=0.390, w=0.921)
        self.HOME_QUATERNION_INVERSE = inverse_quaternion(self.HOME_QUATERNION)
    
    def normalize_orientation(self, raw_quat: Quaternion) -> Quaternion:
        """
        Convert raw cube quaternion to normalized orientation
        where (0,0,0,1) means white top, green front.
        
        Args:
            raw_quat: Raw quaternion from cube
        
        Returns:
            Normalized quaternion
        """
        # Multiply by inverse of home quaternion to get relative rotation
        return multiply_quaternions(raw_quat, self.HOME_QUATERNION_INVERSE)
    
    def denormalize_orientation(self, normalized_quat: Quaternion) -> Quaternion:
        """
        Convert normalized orientation back to raw cube quaternion.
        
        Args:
            normalized_quat: Normalized quaternion
        
        Returns:
            Raw cube quaternion
        """
        # Multiply by home quaternion to get raw rotation
        return multiply_quaternions(normalized_quat, self.HOME_QUATERNION)
    
    def get_face_quaternions(self) -> Dict[str, Quaternion]:
        """Get reference quaternions for standard cube positions."""
        return FACE_QUATERNIONS
    
    def is_factory_default(self, quat: Quaternion) -> bool:
        """
        Check if cube is near factory default orientation.
        
        Args:
            quat: Quaternion to check
        
        Returns:
            True if near factory default (w ≈ -1)
        """
        return abs(quat.w + 1) < 0.1
    
    def filter_noise(self, quat: Quaternion, threshold: float = 0.02) -> Quaternion:
        """
        Filter out sensor noise from quaternion values.
        
        Args:
            quat: Input quaternion
            threshold: Noise threshold
        
        Returns:
            Filtered quaternion
        """
        return Quaternion(
            x=0 if abs(quat.x) < threshold else quat.x,
            y=0 if abs(quat.y) < threshold else quat.y,
            z=0 if abs(quat.z) < threshold else quat.z,
            w=quat.w
        )


def quaternion_to_euler(quat: Quaternion) -> Tuple[float, float, float]:
    """
    Convert quaternion to Euler angles (roll, pitch, yaw) in degrees.
    
    Args:
        quat: Input quaternion
        
    Returns:
        Tuple of (roll, pitch, yaw) in degrees
    """
    # Normalize quaternion first
    norm = math.sqrt(quat.x*quat.x + quat.y*quat.y + quat.z*quat.z + quat.w*quat.w)
    if norm == 0:
        return (0.0, 0.0, 0.0)
    
    x, y, z, w = quat.x/norm, quat.y/norm, quat.z/norm, quat.w/norm
    
    # Roll (x-axis rotation)
    sinr_cosp = 2 * (w * x + y * z)
    cosr_cosp = 1 - 2 * (x * x + y * y)
    roll = math.atan2(sinr_cosp, cosr_cosp)
    
    # Pitch (y-axis rotation)
    sinp = 2 * (w * y - z * x)
    if abs(sinp) >= 1:
        pitch = math.copysign(math.pi / 2, sinp)  # Use 90 degrees if out of range
    else:
        pitch = math.asin(sinp)
    
    # Yaw (z-axis rotation)
    siny_cosp = 2 * (w * z + x * y)
    cosy_cosp = 1 - 2 * (y * y + z * z)
    yaw = math.atan2(siny_cosp, cosy_cosp)
    
    # Convert to degrees
    roll_deg = math.degrees(roll)
    pitch_deg = math.degrees(pitch)
    yaw_deg = math.degrees(yaw)
    
    return (roll_deg, pitch_deg, yaw_deg)