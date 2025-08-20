"""Base protocol interfaces and types for GAN cubes."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Callable
from enum import Enum
import asyncio
from ..utils import Quaternion


class CommandType(Enum):
    """Types of commands that can be sent to the cube."""
    REQUEST_HARDWARE = "REQUEST_HARDWARE"
    REQUEST_FACELETS = "REQUEST_FACELETS"
    REQUEST_BATTERY = "REQUEST_BATTERY"
    REQUEST_RESET = "REQUEST_RESET"


@dataclass
class GanCubeCommand:
    """Command message to send to cube."""
    type: CommandType


@dataclass
class GanCubeMove:
    """Representation of GAN Smart Cube move."""
    face: int  # 0-U, 1-R, 2-F, 3-D, 4-L, 5-B
    direction: int  # 0-CW, 1-CCW
    move: str  # e.g., "R'", "U"
    local_timestamp: Optional[float]  # Host device timestamp
    cube_timestamp: Optional[float]  # Cube internal timestamp


@dataclass
class GanCubeMoveEvent:
    """Move event from cube."""
    serial: int  # 0-255, circular counter
    face: int
    direction: int
    move: str
    local_timestamp: Optional[float] = None
    cube_timestamp: Optional[float] = None
    type: str = "MOVE"


@dataclass
class GanCubeState:
    """Representation of GAN Smart Cube facelets state."""
    CP: List[int]  # Corner Permutation: 8 elements, 0-7
    CO: List[int]  # Corner Orientation: 8 elements, 0-2
    EP: List[int]  # Edge Permutation: 12 elements, 0-11
    EO: List[int]  # Edge Orientation: 12 elements, 0-1


@dataclass
class GanCubeFaceletsEvent:
    """Facelets event from cube."""
    serial: int  # 0-255, circular counter
    facelets: str  # Kociemba notation
    state: Optional[GanCubeState] = None
    type: str = "FACELETS"


@dataclass
class GanCubeAngularVelocity:
    """Angular velocity by axes."""
    x: float
    y: float
    z: float


@dataclass
class GanCubeOrientationEvent:
    """Orientation event from cube."""
    quaternion: Quaternion
    angular_velocity: GanCubeAngularVelocity
    type: str = "ORIENTATION"
    local_timestamp: Optional[float] = None
    cube_timestamp: Optional[float] = None


@dataclass
class GanCubeBatteryEvent:
    """Battery event from cube."""
    percent: int  # 0-100
    type: str = "BATTERY"


@dataclass
class GanCubeHardwareEvent:
    """Hardware information event."""
    model: str
    firmware: str
    protocol: str
    type: str = "HARDWARE"


class GanCubeEvent:
    """Union type for all cube events."""
    pass


class GanCubeProtocol(ABC):
    """
    Base protocol interface for GAN Smart Cubes.
    """
    
    def __init__(self, encrypter=None):
        """
        Initialize protocol with optional encrypter.
        
        Args:
            encrypter: Encryption implementation for this protocol
        """
        self._encrypter = encrypter
        self._last_serial = -1
        self._state = None
        self._orientation_buffer = []
        self._timestamp_sync_points = []
    
    @abstractmethod
    def encode_command(self, command: GanCubeCommand) -> bytes:
        """
        Encode a command to bytes for sending to the cube.
        
        Args:
            command: Command to encode
        
        Returns:
            Encoded command bytes
        """
        pass
    
    @abstractmethod
    def decode_event(self, data: bytes) -> Optional[GanCubeEvent]:
        """
        Decode bytes received from cube into an event.
        
        Args:
            data: Raw bytes from cube
        
        Returns:
            Decoded event or None if not recognized
        """
        pass
    
    @abstractmethod
    def supports_orientation(self) -> bool:
        """Check if this protocol supports orientation events."""
        pass
    
    @abstractmethod
    def get_protocol_name(self) -> str:
        """Get the name of this protocol."""
        pass
    
    
    def _encrypt(self, data: bytes) -> bytes:
        """Encrypt data if encrypter is available."""
        if self._encrypter:
            return self._encrypter.encrypt(data)
        return data
    
    def _decrypt(self, data: bytes) -> bytes:
        """Decrypt data if encrypter is available."""
        if self._encrypter:
            return self._encrypter.decrypt(data)
        return data
    
    @property
    def encrypter(self):
        """Get the encrypter instance."""
        return self._encrypter
    
    @staticmethod
    def _move_to_string(face: int, direction: int) -> str:
        """
        Convert numeric face/direction to standard notation.
        
        Args:
            face: Face index (0-5)
            direction: 0 for CW, 1 for CCW
        
        Returns:
            Move string like "R" or "U'"
        """
        faces = ['U', 'R', 'F', 'D', 'L', 'B']
        if face < 0 or face >= len(faces):
            return 'X'
        move = faces[face]
        if direction == 1:
            move += "'"
        return move