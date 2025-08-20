"""GAN Gen2 protocol implementation."""

import struct
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from .base import (
    GanCubeProtocol, GanCubeCommand, CommandType,
    GanCubeMoveEvent, GanCubeFaceletsEvent, GanCubeState,
    GanCubeOrientationEvent, GanCubeBatteryEvent, GanCubeHardwareEvent,
    GanCubeAngularVelocity
)
from ..utils import (
    now, to_kociemba_facelets, smooth_orientation_data,
    cube_timestamp_linear_fit, Quaternion
)


class ProtocolMessageView:
    """Helper class for bit-level message parsing."""
    
    def __init__(self, data: bytes):
        self.data = data
        # Convert bytes to bit string like in TypeScript implementation
        self.bits = ''.join(f'{byte:08b}' for byte in data)
    
    def get_bit_word(self, bit_offset: int, bit_length: int, little_endian: bool = False) -> int:
        """
        Extract bits from message.
        
        Args:
            bit_offset: Starting bit position
            bit_length: Number of bits to extract
            little_endian: Whether to interpret multi-byte values as little endian
        
        Returns:
            Extracted value as integer
        """
        if bit_length <= 8:
            # Simple case: extract from bit string
            bit_slice = self.bits[bit_offset:bit_offset + bit_length]
            return int(bit_slice, 2) if bit_slice else 0
        elif bit_length in (16, 32):
            # Multi-byte case: extract byte by byte then combine
            num_bytes = bit_length // 8
            bytes_data = bytearray()
            
            for i in range(num_bytes):
                byte_start = bit_offset + (8 * i)
                byte_end = byte_start + 8
                byte_bits = self.bits[byte_start:byte_end]
                if byte_bits:
                    bytes_data.append(int(byte_bits, 2))
                else:
                    bytes_data.append(0)
            
            # Convert to integer with proper endianness
            if bit_length == 16:
                import struct
                return struct.unpack('<H' if little_endian else '>H', bytes_data)[0]
            else:  # 32-bit
                import struct
                return struct.unpack('<I' if little_endian else '>I', bytes_data)[0]
        else:
            # Fallback for other sizes
            bit_slice = self.bits[bit_offset:bit_offset + bit_length]
            return int(bit_slice, 2) if bit_slice else 0


class GanGen2Protocol(GanCubeProtocol):
    """
    Driver implementation for GAN Gen2 protocol.
    
    Supported cubes:
    - GAN Mini ui FreePlay
    - GAN12 ui
    - GAN356 i, i2, i Play, i Carry S
    - Monster Go 3Ai
    - MoYu AI 2023
    """
    
    def __init__(self, encrypter=None):
        super().__init__(encrypter)
        self.last_serial = -1
        self.last_move_timestamp = 0
        self.cube_timestamp = 0
        
        # Gyroscope smoothing
        self.gyro_buffer = []
        self.GYRO_BUFFER_SIZE = 5
        self.GYRO_RATE_LIMIT_MS = 16  # 60 FPS max
        self.last_gyro_emit = 0
        
        # Timestamp synchronization
        self.gyro_timestamp_history = []
        self.MAX_TIMESTAMP_HISTORY = 20
    
    def get_protocol_name(self) -> str:
        return "GAN_GEN2"
    
    def supports_orientation(self) -> bool:
        return True
    
    def encode_command(self, command: GanCubeCommand) -> bytes:
        """Encode command for Gen2 protocol."""
        msg = bytearray(20)
        
        if command.type == CommandType.REQUEST_FACELETS:
            msg[0] = 0x04
        elif command.type == CommandType.REQUEST_HARDWARE:
            msg[0] = 0x05
        elif command.type == CommandType.REQUEST_BATTERY:
            msg[0] = 0x09
        elif command.type == CommandType.REQUEST_RESET:
            reset_data = bytes([
                0x0A, 0x05, 0x39, 0x77, 0x00, 0x00, 0x01, 0x23,
                0x45, 0x67, 0x89, 0xAB, 0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00
            ])
            msg[:len(reset_data)] = reset_data
        else:
            return None
        
        # Encrypt if encrypter available
        return self._encrypt(bytes(msg))
    
    def decode_event(self, data: bytes) -> Optional[List[Any]]:
        """Decode event from Gen2 protocol."""
        # Decrypt if encrypter available
        data = self._decrypt(data)
        
        timestamp = now()
        events = []
        msg = ProtocolMessageView(data)
        event_type = msg.get_bit_word(0, 4)
        
        if event_type == 0x01:  # GYRO/ORIENTATION
            events.extend(self._handle_gyro_event(msg, timestamp))
        elif event_type == 0x02:  # MOVE
            events.extend(self._handle_move_event(msg, timestamp))
        elif event_type == 0x03:  # FACELETS (some cubes use 0x03 instead of 0x04)
            events.extend(self._handle_facelets_event(msg, timestamp))
        elif event_type == 0x04:  # FACELETS
            events.extend(self._handle_facelets_event(msg, timestamp))
        elif event_type == 0x05:  # HARDWARE
            events.extend(self._handle_hardware_event(msg, timestamp))
        elif event_type == 0x09:  # BATTERY
            events.extend(self._handle_battery_event(msg, timestamp))
        elif event_type == 0x0D:  # DISCONNECT
            # Signal disconnect
            pass
        
        return events if events else None
    
    def _handle_gyro_event(self, msg: ProtocolMessageView, timestamp: float) -> List[Any]:
        """Handle gyroscope/orientation event."""
        # Parse quaternion data
        qw = msg.get_bit_word(4, 16)
        qx = msg.get_bit_word(20, 16)
        qy = msg.get_bit_word(36, 16)
        qz = msg.get_bit_word(52, 16)
        
        # Convert to normalized quaternion
        quaternion = Quaternion(
            x=(1 - (qx >> 15) * 2) * (qx & 0x7FFF) / 0x7FFF,
            y=(1 - (qy >> 15) * 2) * (qy & 0x7FFF) / 0x7FFF,
            z=(1 - (qz >> 15) * 2) * (qz & 0x7FFF) / 0x7FFF,
            w=(1 - (qw >> 15) * 2) * (qw & 0x7FFF) / 0x7FFF
        )
        
        # Process through smoothing
        event = self._process_gyro_data(quaternion, timestamp)
        return [event] if event else []
    
    def _process_gyro_data(self, quaternion: Quaternion, timestamp: float, 
                          cube_timestamp: Optional[float] = None) -> Optional[GanCubeOrientationEvent]:
        """Process and smooth gyroscope data."""
        # Rate limiting
        if timestamp - self.last_gyro_emit < self.GYRO_RATE_LIMIT_MS:
            return None
        
        # Update timestamp sync if available
        if cube_timestamp is not None:
            self._update_timestamp_sync(cube_timestamp, timestamp)
        
        # Add to buffer
        self.gyro_buffer.append({
            'quaternion': quaternion,
            'timestamp': timestamp
        })
        
        # Maintain buffer size
        if len(self.gyro_buffer) > self.GYRO_BUFFER_SIZE:
            self.gyro_buffer.pop(0)
        
        # Apply smoothing
        smoothed = smooth_orientation_data(
            self.gyro_buffer,
            min(3, len(self.gyro_buffer))
        )
        
        if smoothed:
            self.last_gyro_emit = timestamp
            velocity = self._calculate_angular_velocity()
            
            return GanCubeOrientationEvent(
                type="ORIENTATION",
                quaternion=smoothed,
                angular_velocity=velocity or GanCubeAngularVelocity(0, 0, 0),
                local_timestamp=timestamp,
                cube_timestamp=cube_timestamp
            )
        
        return None
    
    def _update_timestamp_sync(self, cube_time: float, host_time: float):
        """Update timestamp synchronization data."""
        self.gyro_timestamp_history.append({
            'cube_time': cube_time,
            'host_time': host_time
        })
        
        # Maintain history size
        if len(self.gyro_timestamp_history) > self.MAX_TIMESTAMP_HISTORY:
            self.gyro_timestamp_history.pop(0)
    
    def _get_synchronized_timestamp(self, cube_timestamp: float) -> float:
        """Get synchronized timestamp using linear regression."""
        if len(self.gyro_timestamp_history) < 2:
            return now()
        
        fit = cube_timestamp_linear_fit(self.gyro_timestamp_history)
        return round(fit.slope * cube_timestamp + fit.intercept)
    
    def _calculate_angular_velocity(self) -> Optional[GanCubeAngularVelocity]:
        """Calculate angular velocity from recent orientations."""
        if len(self.gyro_buffer) < 2:
            return None
        
        recent = self.gyro_buffer[-2:]
        dt = (recent[1]['timestamp'] - recent[0]['timestamp']) / 1000  # to seconds
        
        if dt <= 0:
            return None
        
        q1 = recent[0]['quaternion']
        q2 = recent[1]['quaternion']
        
        return GanCubeAngularVelocity(
            x=(q2.x - q1.x) / dt,
            y=(q2.y - q1.y) / dt,
            z=(q2.z - q1.z) / dt
        )
    
    def _handle_move_event(self, msg: ProtocolMessageView, timestamp: float) -> List[GanCubeMoveEvent]:
        """Handle move event."""
        events = []
        
        # Only accept moves after first facelets event
        if self.last_serial == -1:
            return events
        
        serial = msg.get_bit_word(4, 8)
        diff = min((serial - self.last_serial) & 0xFF, 7)
        self.last_serial = serial
        
        if diff > 0:
            for i in range(diff - 1, -1, -1):
                face = msg.get_bit_word(12 + 5 * i, 4)
                direction = msg.get_bit_word(16 + 5 * i, 1)
                move = self._move_to_string(face, direction)
                
                elapsed = msg.get_bit_word(47 + 16 * i, 16)
                if elapsed == 0:  # Handle timestamp overflow
                    elapsed = timestamp - self.last_move_timestamp
                
                self.cube_timestamp += elapsed
                
                events.append(GanCubeMoveEvent(
                    type="MOVE",
                    serial=(serial - i) & 0xFF,
                    face=face,
                    direction=direction,
                    move=move,
                    local_timestamp=timestamp if i == 0 else None,
                    cube_timestamp=self.cube_timestamp
                ))
            
            self.last_move_timestamp = timestamp
        
        return events
    
    def _handle_facelets_event(self, msg: ProtocolMessageView, timestamp: float) -> List[GanCubeFaceletsEvent]:
        """Handle facelets state event."""
        serial = msg.get_bit_word(4, 8)
        
        if self.last_serial == -1:
            self.last_serial = serial
        
        # Parse corner/edge permutation and orientation
        cp = []
        co = []
        ep = []
        eo = []
        
        # Corners
        for i in range(7):
            cp.append(msg.get_bit_word(12 + i * 3, 3))
            co.append(msg.get_bit_word(33 + i * 2, 2))
        
        # Calculate parity for last corner
        cp.append((28 - sum(cp)) % 8)
        co.append((3 - (sum(co) % 3)) % 3)
        
        # Edges
        for i in range(11):
            ep.append(msg.get_bit_word(47 + i * 4, 4))
            eo.append(msg.get_bit_word(91 + i, 1))
        
        # Calculate parity for last edge
        ep.append((66 - sum(ep)) % 12)
        eo.append((2 - (sum(eo) % 2)) % 2)
        
        state = GanCubeState(CP=cp, CO=co, EP=ep, EO=eo)
        facelets = to_kociemba_facelets(cp, co, ep, eo)
        
        return [GanCubeFaceletsEvent(
            type="FACELETS",
            serial=serial,
            facelets=facelets,
            state=state
        )]
    
    def _handle_hardware_event(self, msg: ProtocolMessageView, timestamp: float) -> List[GanCubeHardwareEvent]:
        """Handle hardware information event."""
        hw_major = msg.get_bit_word(8, 8)
        hw_minor = msg.get_bit_word(16, 8)
        sw_major = msg.get_bit_word(24, 8)
        sw_minor = msg.get_bit_word(32, 8)
        gyro_supported = msg.get_bit_word(104, 1)
        
        # Parse hardware name
        hardware_name = ''
        for i in range(8):
            char_code = msg.get_bit_word(i * 8 + 40, 8)
            if char_code:
                hardware_name += chr(char_code)
        
        return [GanCubeHardwareEvent(
            type="HARDWARE",
            model=hardware_name.strip(),
            firmware=f"{sw_major}.{sw_minor}",
            protocol="GEN2"
        )]
    
    def _handle_battery_event(self, msg: ProtocolMessageView, timestamp: float) -> List[GanCubeBatteryEvent]:
        """Handle battery level event."""
        battery_level = msg.get_bit_word(8, 8)
        
        return [GanCubeBatteryEvent(
            type="BATTERY",
            percent=min(battery_level, 100)
        )]
    
    def _move_to_string(self, face: int, direction: int) -> str:
        """Convert face and direction to move notation."""
        face_chars = "URFDLB"
        if 0 <= face < len(face_chars):
            face_char = face_chars[face]
            return face_char + "'" if direction == 1 else face_char
        return "?"
    
    def _encrypt(self, data: bytes) -> bytes:
        """Encrypt data using encrypter if available."""
        if self.encrypter:
            return self.encrypter.encrypt(data)
        return data
    
    def _decrypt(self, data: bytes) -> bytes:
        """Decrypt data using encrypter if available."""
        if self.encrypter:
            return self.encrypter.decrypt(data)
        return data