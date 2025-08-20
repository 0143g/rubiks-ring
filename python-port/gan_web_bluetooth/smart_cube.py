"""GAN Smart Cube implementation using bleak."""

import asyncio
import struct
from typing import Optional, Callable, List, Dict, Any, Union
from dataclasses import dataclass
try:
    from bleak import BleakClient, BleakScanner, BLEDevice
    from bleak.backends.device import BLEDevice
    from bleak.backends.scanner import AdvertisementData
except ImportError:
    # Fallback for systems without proper Bluetooth support
    BleakClient = BleakScanner = BLEDevice = AdvertisementData = None
from .event_emitter import EventEmitter

from . import definitions as defs
from .protocols import (
    GanCubeProtocol, CommandType,
    GanCubeCommand, GanCubeMoveEvent, GanCubeFaceletsEvent,
    GanCubeOrientationEvent, GanCubeBatteryEvent, GanCubeHardwareEvent
)
from .protocols.gen2 import GanGen2Protocol
from .encryption import (
    GanGen2CubeEncrypter, GanGen3CubeEncrypter, GanGen4CubeEncrypter
)
from .utils import now
from .platform_utils import is_bluetooth_available, MockBleakScanner, MockBleakClient, print_bluetooth_help


class GanSmartCube:
    """
    GAN Smart Cube connection and control.
    
    Supports automatic protocol detection for:
    - Gen2: GAN Mini ui FreePlay, GAN12 ui, GAN356 i series, Monster Go 3Ai, MoYu AI 2023
    - Gen3: GAN356 i Carry 2
    - Gen4: GAN12 ui Maglev, GAN14 ui FreePlay
    
    Example:
        cube = GanSmartCube()
        await cube.connect()
        
        cube.on('move', lambda move: print(f"Move: {move.move}"))
        cube.on('facelets', lambda evt: print(f"State: {evt.facelets}"))
        cube.on('orientation', lambda evt: print(f"Orientation: {evt.quaternion}"))
        
        # Request current state
        state = await cube.get_state()
        print(f"Current state: {state}")
        
        # Wait for cube events
        await asyncio.sleep(60)
        
        await cube.disconnect()
    """
    
    def __init__(self, mac_address_provider: Optional[Callable] = None):
        """
        Initialize GAN Smart Cube.
        
        Args:
            mac_address_provider: Optional function to provide MAC address
                                 for encryption. If None, will try to extract
                                 from advertisement data.
        """
        self._client: Optional[BleakClient] = None
        self._protocol: Optional[GanCubeProtocol] = None
        self._event_emitter = EventEmitter()
        self._connected = False
        self._mac_provider = mac_address_provider
        self._command_char = None
        self._state_char = None
        self._device_info = {}
    
    def on(self, event: str, handler: Callable):
        """
        Register event handler.
        
        Events:
        - 'move': Cube move detected (GanCubeMoveEvent)
        - 'facelets': Facelets state update (GanCubeFaceletsEvent)
        - 'orientation': Orientation update (GanCubeOrientationEvent)
        - 'battery': Battery level update (GanCubeBatteryEvent)
        - 'hardware': Hardware info received (GanCubeHardwareEvent)
        - 'connected': Connected to cube
        - 'disconnected': Disconnected from cube
        
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
        Connect to GAN Smart Cube.
        
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
        device = None
        mac_address = None
        
        if not device_address:
            device, mac_address = await self._scan_for_cube()
            if not device:
                raise RuntimeError("No GAN Smart Cube found")
            device_address = device.address
        
        # Get MAC address for encryption
        if not mac_address:
            if self._mac_provider:
                mac_address = await self._mac_provider(device_address)
            else:
                # Try to extract from manufacturer data during scan
                mac_address = await self._get_mac_from_scan(device_address)
        
        # If still no MAC, try using the device address as fallback
        if not mac_address:
            print(f"Warning: No MAC address found, using device address as fallback")
            mac_address = device_address
        
        # Create encryption salt from MAC (reversed)
        mac_bytes = [int(x, 16) for x in mac_address.split(':')]
        salt = bytes(reversed(mac_bytes))
        
        # Connect to device
        print(f"Connecting to device at {device_address}...")
        self._client = BleakClient(device_address)
        await self._client.connect()
        print(f"Connected! Device is connected: {self._client.is_connected}")
        
        # Get services and detect protocol
        print("Discovering services...")
        services = self._client.services
        service_list = list(services)
        print(f"Found {len(service_list)} services:")
        for service in service_list:
            print(f"  Service: {service.uuid}")
        
        # Try to detect and setup protocol
        protocol_found = False
        
        # Check for Gen2 protocol
        print(f"Looking for Gen2 service: {defs.GAN_GEN2_SERVICE}")
        if services.get_service(defs.GAN_GEN2_SERVICE):
            print("✓ Found Gen2 service")
            service = services.get_service(defs.GAN_GEN2_SERVICE)
            self._command_char = service.get_characteristic(defs.GAN_GEN2_COMMAND_CHARACTERISTIC)
            self._state_char = service.get_characteristic(defs.GAN_GEN2_STATE_CHARACTERISTIC)
            
            # Determine encryption key (MoYu AI uses different key)
            device_name = device.name if device else ""
            key_index = 1 if device_name.startswith('AiCube') else 0
            key_data = defs.GAN_ENCRYPTION_KEYS[key_index]
            
            encrypter = GanGen2CubeEncrypter(
                bytes(key_data['key']),
                bytes(key_data['iv']),
                salt
            )
            self._protocol = GanGen2Protocol(encrypter)
            protocol_found = True
            print("✓ Gen2 protocol configured")
            
        # Check for Gen3 protocol
        elif services.get_service(defs.GAN_GEN3_SERVICE):
            print("✓ Found Gen3 service")
            service = services.get_service(defs.GAN_GEN3_SERVICE)
            self._command_char = service.get_characteristic(defs.GAN_GEN3_COMMAND_CHARACTERISTIC)
            self._state_char = service.get_characteristic(defs.GAN_GEN3_STATE_CHARACTERISTIC)
            
            key_data = defs.GAN_ENCRYPTION_KEYS[0]
            encrypter = GanGen3CubeEncrypter(
                bytes(key_data['key']),
                bytes(key_data['iv']),
                salt
            )
            # Note: Gen3 protocol implementation would go here
            # For now, using Gen2 as placeholder
            self._protocol = GanGen2Protocol(encrypter)
            protocol_found = True
            
        # Check for Gen4 protocol
        elif services.get_service(defs.GAN_GEN4_SERVICE):
            print("✓ Found Gen4 service")
            service = services.get_service(defs.GAN_GEN4_SERVICE)
            self._command_char = service.get_characteristic(defs.GAN_GEN4_COMMAND_CHARACTERISTIC)
            self._state_char = service.get_characteristic(defs.GAN_GEN4_STATE_CHARACTERISTIC)
            
            key_data = defs.GAN_ENCRYPTION_KEYS[0]
            encrypter = GanGen4CubeEncrypter(
                bytes(key_data['key']),
                bytes(key_data['iv']),
                salt
            )
            # Note: Gen4 protocol implementation would go here
            # For now, using Gen2 as placeholder
            self._protocol = GanGen2Protocol(encrypter)
            protocol_found = True
        
        if not protocol_found:
            await self._client.disconnect()
            raise RuntimeError("Unsupported cube model or protocol")
        
        # Subscribe to state notifications
        await self._client.start_notify(
            self._state_char,
            self._handle_state_notification
        )
        
        self._connected = True
        self._event_emitter.emit('connected', None)
        
        # Request initial hardware info
        await self.request_hardware_info()
    
    async def disconnect(self) -> None:
        """Disconnect from cube."""
        if not self._connected or not self._client:
            return
        
        try:
            if self._state_char:
                await self._client.stop_notify(self._state_char)
        except:
            pass
        
        try:
            await self._client.disconnect()
        except:
            pass
        
        self._connected = False
        self._client = None
        self._protocol = None
        self._event_emitter.emit('disconnected', None)
    
    async def get_state(self) -> Optional[str]:
        """
        Request current cube state.
        
        Returns:
            Facelets string in Kociemba notation or None
        """
        if not self._connected:
            raise RuntimeError("Not connected to cube")
        
        # Send request facelets command
        cmd = GanCubeCommand(type=CommandType.REQUEST_FACELETS)
        await self._send_command(cmd)
        
        # Wait for facelets event (with timeout)
        # Note: In production, this would use proper event waiting
        await asyncio.sleep(0.5)
        
        return None  # Placeholder
    
    async def request_battery(self) -> None:
        """Request battery level from cube."""
        if not self._connected:
            raise RuntimeError("Not connected to cube")
        
        cmd = GanCubeCommand(type=CommandType.REQUEST_BATTERY)
        await self._send_command(cmd)
    
    async def request_hardware_info(self) -> None:
        """Request hardware information from cube."""
        if not self._connected:
            raise RuntimeError("Not connected to cube")
        
        cmd = GanCubeCommand(type=CommandType.REQUEST_HARDWARE)
        await self._send_command(cmd)
    
    async def reset_state(self) -> None:
        """Reset cube internal state to solved."""
        if not self._connected:
            raise RuntimeError("Not connected to cube")
        
        cmd = GanCubeCommand(type=CommandType.REQUEST_RESET)
        await self._send_command(cmd)
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to cube."""
        return self._connected
    
    @property
    def device_info(self) -> Dict[str, Any]:
        """Get device information."""
        return self._device_info.copy()
    
    async def _scan_for_cube(self) -> tuple[Optional[BLEDevice], Optional[str]]:
        """
        Scan for GAN Smart Cube device.
        
        Returns:
            Tuple of (device, mac_address)
        """
        print("Scanning for devices...")
        
        # First try a general scan to see what's available
        devices = await BleakScanner.discover(timeout=3.0)
        
        print(f"Found {len(devices)} devices:")
        for device in devices:
            name = device.name or "Unknown"
            print(f"  {device.address}: {name}")
        
        # Look for GAN cube by name
        for device in devices:
            if device.name and any(
                device.name.startswith(prefix)
                for prefix in ["GAN", "MG", "AiCube"]
            ):
                print(f"Found potential GAN cube: {device.name} at {device.address}")
                return device, device.address
        
        return None, None
    
    async def _get_mac_from_scan(self, device_address: str) -> Optional[str]:
        """
        Try to get MAC address from advertisement scan.
        
        Args:
            device_address: BLE device address
        
        Returns:
            MAC address string or None
        """
        mac_address = None
        
        def detection_callback(device: BLEDevice, advertisement_data: AdvertisementData):
            nonlocal mac_address
            
            if device.address == device_address:
                if advertisement_data.manufacturer_data:
                    mac_address = self._extract_mac_from_manufacturer_data(
                        advertisement_data.manufacturer_data
                    )
                    if mac_address:
                        return True
            return False
        
        # Scan for a short time to get manufacturer data
        await BleakScanner.find_device_by_filter(
            detection_callback,
            timeout=5.0
        )
        
        return mac_address
    
    def _extract_mac_from_manufacturer_data(self, manufacturer_data: Dict[int, bytes]) -> Optional[str]:
        """
        Extract MAC address from manufacturer data.
        
        Args:
            manufacturer_data: Manufacturer data from advertisement
        
        Returns:
            MAC address string or None
        """
        # Check all known GAN CICs
        for cic in defs.GAN_CIC_LIST:
            if cic in manufacturer_data:
                data = manufacturer_data[cic]
                if len(data) >= 9:
                    # MAC is in last 6 bytes, reversed
                    mac_bytes = data[3:9]
                    mac = ':'.join(f"{b:02X}" for b in reversed(mac_bytes))
                    return mac
        return None
    
    async def _send_command(self, command: GanCubeCommand) -> None:
        """Send command to cube."""
        if not self._protocol or not self._command_char:
            return
        
        data = self._protocol.encode_command(command)
        if data:
            await self._client.write_gatt_char(self._command_char, data)
    
    def _handle_state_notification(self, sender, data: bytes):
        """Handle state notification from cube."""
        if not self._protocol:
            return
        
        events = self._protocol.decode_event(data)
        if not events:
            return
        
        # Process and emit events
        for event in events:
            if isinstance(event, GanCubeMoveEvent):
                self._event_emitter.emit('move', event)
            elif isinstance(event, GanCubeFaceletsEvent):
                self._event_emitter.emit('facelets', event)
            elif isinstance(event, GanCubeOrientationEvent):
                self._event_emitter.emit('orientation', event)
            elif isinstance(event, GanCubeBatteryEvent):
                self._event_emitter.emit('battery', event)
            elif isinstance(event, GanCubeHardwareEvent):
                self._device_info.update({
                    'model': event.model,
                    'firmware': event.firmware,
                    'protocol': event.protocol
                })
                self._event_emitter.emit('hardware', event)
