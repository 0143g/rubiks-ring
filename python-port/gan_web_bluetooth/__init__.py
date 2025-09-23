"""
GAN Web Bluetooth Python Library

A Python port of the gan-web-bluetooth TypeScript library for interacting
with GAN Smart Timers and Smart Cubes via Bluetooth Low Energy.
"""

__version__ = "0.1.0"

# Import main classes
from .smart_timer import (
    GanSmartTimer,
    GanTimerState,
    GanTimerTime,
    GanTimerEvent,
    GanTimerRecordedTimes
)

from .smart_cube import GanSmartCube

from .utils import (
    Quaternion,
    CubeOrientationTransform,
    to_kociemba_facelets,
    now
)

from .protocols import (
    GanCubeMove,
    GanCubeMoveEvent,
    GanCubeState,
    GanCubeFaceletsEvent,
    GanCubeOrientationEvent,
    GanCubeBatteryEvent,
    GanCubeHardwareEvent,
    CommandType
)

# Export main classes and functions
__all__ = [
    # Timer
    'GanSmartTimer',
    'GanTimerState',
    'GanTimerTime',
    'GanTimerEvent',
    'GanTimerRecordedTimes',
    
    # Cube
    'GanSmartCube',
    
    # Events
    'GanCubeMove',
    'GanCubeMoveEvent',
    'GanCubeState',
    'GanCubeFaceletsEvent',
    'GanCubeOrientationEvent',
    'GanCubeBatteryEvent',
    'GanCubeHardwareEvent',
    'CommandType',
    
    # Utils
    'Quaternion',
    'CubeOrientationTransform',
    'to_kociemba_facelets',
    'now',
]
