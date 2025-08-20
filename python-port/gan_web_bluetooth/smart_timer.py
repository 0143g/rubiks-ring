"""GAN Smart Timer implementation using bleak."""

import asyncio
import struct
from typing import Optional, Callable, List, Dict, Any
from dataclasses import dataclass
from enum import IntEnum
try:
    from bleak import BleakClient, BleakScanner
except ImportError:
    BleakClient = BleakScanner = None
from .event_emitter import EventEmitter

from .definitions import GAN_TIMER_SERVICE
from .platform_utils import is_bluetooth_available, print_bluetooth_help


# Timer-specific UUIDs
GAN_TIMER_TIME_CHARACTERISTIC = "0000fff2-0000-1000-8000-00805f9b34fb"
GAN_TIMER_STATE_CHARACTERISTIC = "0000fff5-0000-1000-8000-00805f9b34fb"


class GanTimerState(IntEnum):
    """GAN Smart Timer states."""
    DISCONNECT = 0
    GET_SET = 1      # Grace delay expired, ready to start
    HANDS_OFF = 2    # Hands removed before grace delay
    RUNNING = 3      # Timer is running
    STOPPED = 4      # Timer stopped, includes recorded time
    IDLE = 5         # Timer is reset and idle
    HANDS_ON = 6     # Hands placed on timer
    FINISHED = 7     # State after STOPPED


@dataclass
class GanTimerTime:
    """Representation of time value."""
    minutes: int
    seconds: int
    milliseconds: int
    
    @property
    def as_timestamp(self) -> int:
        """Get time as milliseconds timestamp."""
        return 60000 * self.minutes + 1000 * self.seconds + self.milliseconds
    
    def __str__(self) -> str:
        """String representation in M:SS.mmm format."""
        return f"{self.minutes}:{self.seconds:02d}.{self.milliseconds:03d}"
    
    @classmethod
    def from_raw(cls, data: bytes, offset: int = 0) -> 'GanTimerTime':
        """Create from raw timer data."""
        minutes = data[offset]
        seconds = data[offset + 1]
        milliseconds = struct.unpack('<H', data[offset + 2:offset + 4])[0]
        return cls(minutes, seconds, milliseconds)
    
    @classmethod
    def from_timestamp(cls, timestamp: int) -> 'GanTimerTime':
        """Create from milliseconds timestamp."""
        minutes = timestamp // 60000
        seconds = (timestamp % 60000) // 1000
        milliseconds = timestamp % 1000
        return cls(minutes, seconds, milliseconds)


@dataclass
class GanTimerEvent:
    """Timer state event."""
    state: GanTimerState
    recorded_time: Optional[GanTimerTime] = None


@dataclass
class GanTimerRecordedTimes:
    """Recorded time values from timer memory."""
    display_time: GanTimerTime
    previous_times: List[GanTimerTime]


class GanSmartTimer:
    """
    GAN Smart Timer connection and control.
    
    Example:
        timer = GanSmartTimer()
        await timer.connect()
        
        timer.on('state_change', lambda evt: print(f"State: {evt.state}"))
        timer.on('time_update', lambda time: print(f"Time: {time}"))
        
        # Wait for timer events
        await asyncio.sleep(60)
        
        await timer.disconnect()
    """
    
    def __init__(self):
        """Initialize GAN Smart Timer."""
        self._client: Optional[BleakClient] = None
        self._event_emitter = EventEmitter()
        self._connected = False
        self._time_characteristic = None
        self._state_characteristic = None
    
    def on(self, event: str, handler: Callable):
        """
        Register event handler.
        
        Events:
        - 'state_change': Timer state changed (GanTimerEvent)
        - 'time_update': Time recorded (GanTimerTime)
        - 'connected': Connected to timer
        - 'disconnected': Disconnected from timer
        
        Args:
            event: Event name
            handler: Handler function
        """
        self._event_emitter.on(event, handler)
    
    def off(self, event: str, handler: Callable = None):
        """
        Unregister event handler.
        
        Args:
            event: Event name
            handler: Handler to remove, or None to remove all
        """
        if handler:
            self._event_emitter.remove_listener(event, handler)
        else:
            self._event_emitter.remove_all_listeners(event)
    
    async def connect(self, device_address: Optional[str] = None) -> None:
        """
        Connect to GAN Smart Timer.
        
        Args:
            device_address: Optional BLE address, if None will scan for device
        """
        if self._connected:
            return
        
        # Check if Bluetooth is available on this platform
        if not is_bluetooth_available():
            print_bluetooth_help()
            raise RuntimeError(
                "Bluetooth not available on this platform. "
                "See help above for setup instructions."
            )
        
        # Find device if no address provided
        if not device_address:
            device = await self._scan_for_timer()
            if not device:
                raise RuntimeError("No GAN Smart Timer found")
            device_address = device.address
        
        # Connect to device
        self._client = BleakClient(device_address)
        await self._client.connect()
        
        # Get service and characteristics
        services = await self._client.get_services()
        timer_service = services.get_service(GAN_TIMER_SERVICE)
        
        if not timer_service:
            await self._client.disconnect()
            raise RuntimeError("Timer service not found")
        
        self._time_characteristic = timer_service.get_characteristic(
            GAN_TIMER_TIME_CHARACTERISTIC
        )
        self._state_characteristic = timer_service.get_characteristic(
            GAN_TIMER_STATE_CHARACTERISTIC
        )
        
        if not self._time_characteristic or not self._state_characteristic:
            await self._client.disconnect()
            raise RuntimeError("Required characteristics not found")
        
        # Subscribe to state notifications
        await self._client.start_notify(
            self._state_characteristic,
            self._handle_state_notification
        )
        
        self._connected = True
        self._event_emitter.emit('connected', None)
    
    async def disconnect(self) -> None:
        """Disconnect from timer."""
        if not self._connected or not self._client:
            return
        
        try:
            if self._state_characteristic:
                await self._client.stop_notify(self._state_characteristic)
        except:
            pass
        
        try:
            await self._client.disconnect()
        except:
            pass
        
        self._connected = False
        self._client = None
        self._event_emitter.emit('disconnected', None)
    
    async def get_recorded_times(self) -> GanTimerRecordedTimes:
        """
        Retrieve last recorded times from timer.
        
        Returns:
            Recorded times including display time and previous 3 times
        """
        if not self._connected or not self._time_characteristic:
            raise RuntimeError("Not connected to timer")
        
        data = await self._client.read_gatt_char(self._time_characteristic)
        
        if len(data) < 16:
            raise ValueError("Invalid time data received from timer")
        
        display_time = GanTimerTime.from_raw(data, 0)
        previous_times = [
            GanTimerTime.from_raw(data, 4),
            GanTimerTime.from_raw(data, 8),
            GanTimerTime.from_raw(data, 12)
        ]
        
        return GanTimerRecordedTimes(
            display_time=display_time,
            previous_times=previous_times
        )
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to timer."""
        return self._connected
    
    async def _scan_for_timer(self) -> Optional[Any]:
        """Scan for GAN Smart Timer device."""
        def detection_callback(device, advertisement_data):
            # Check for GAN timer by name
            if device.name and any(
                device.name.startswith(prefix) 
                for prefix in ["GAN", "gan", "Gan"]
            ):
                # Check if it has timer service
                if GAN_TIMER_SERVICE in (advertisement_data.service_uuids or []):
                    return True
            return False
        
        device = await BleakScanner.find_device_by_filter(detection_callback)
        return device
    
    def _handle_state_notification(self, sender, data: bytes):
        """Handle state change notification from timer."""
        if not self._validate_event_data(data):
            return
        
        event = self._parse_timer_event(data)
        
        # Emit state change event
        self._event_emitter.emit('state_change', event)
        
        # If stopped, also emit time update
        if event.state == GanTimerState.STOPPED and event.recorded_time:
            self._event_emitter.emit('time_update', event.recorded_time)
    
    def _validate_event_data(self, data: bytes) -> bool:
        """
        Validate timer event data using CRC check.
        
        Args:
            data: Raw event data
        
        Returns:
            True if data is valid
        """
        if len(data) == 0 or data[0] != 0xFE:
            return False
        
        # Extract CRC from data
        event_crc = struct.unpack('<H', data[-2:])[0]
        
        # Calculate CRC for data portion
        calculated_crc = self._crc16_ccit(data[2:-2])
        
        return event_crc == calculated_crc
    
    def _crc16_ccit(self, data: bytes) -> int:
        """
        Calculate CRC-16/CCIT-FALSE checksum.
        
        Args:
            data: Data to checksum
        
        Returns:
            16-bit CRC value
        """
        crc = 0xFFFF
        
        for byte in data:
            crc ^= byte << 8
            for _ in range(8):
                if crc & 0x8000:
                    crc = ((crc << 1) ^ 0x1021) & 0xFFFF
                else:
                    crc = (crc << 1) & 0xFFFF
        
        return crc
    
    def _parse_timer_event(self, data: bytes) -> GanTimerEvent:
        """
        Parse timer event from raw data.
        
        Args:
            data: Validated event data
        
        Returns:
            Parsed timer event
        """
        state = GanTimerState(data[3])
        
        event = GanTimerEvent(state=state)
        
        # If stopped, extract recorded time
        if state == GanTimerState.STOPPED and len(data) >= 8:
            event.recorded_time = GanTimerTime.from_raw(data, 4)
        
        return event