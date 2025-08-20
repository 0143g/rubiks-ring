"""GAN Cube and Timer Bluetooth definitions and constants."""

from typing import List, Dict, Any

# GAN Gen2 protocol BLE UUIDs
GAN_GEN2_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dc4179"
GAN_GEN2_COMMAND_CHARACTERISTIC = "28be4a4a-cd67-11e9-a32f-2a2ae2dbcce4"
GAN_GEN2_STATE_CHARACTERISTIC = "28be4cb6-cd67-11e9-a32f-2a2ae2dbcce4"

# GAN Gen3 protocol BLE UUIDs
GAN_GEN3_SERVICE = "8653000a-43e6-47b7-9cb0-5fc21d4ae340"
GAN_GEN3_COMMAND_CHARACTERISTIC = "8653000c-43e6-47b7-9cb0-5fc21d4ae340"
GAN_GEN3_STATE_CHARACTERISTIC = "8653000b-43e6-47b7-9cb0-5fc21d4ae340"

# GAN Gen4 protocol BLE UUIDs
GAN_GEN4_SERVICE = "00000010-0000-fff7-fff6-fff5fff4fff0"
GAN_GEN4_COMMAND_CHARACTERISTIC = "0000fff5-0000-1000-8000-00805f9b34fb"
GAN_GEN4_STATE_CHARACTERISTIC = "0000fff6-0000-1000-8000-00805f9b34fb"

# List of Company Identifier Codes for GAN cubes [0x0001, 0xFF01]
GAN_CIC_LIST: List[int] = [(i << 8) | 0x01 for i in range(256)]

# Encryption keys for different GAN cube models
GAN_ENCRYPTION_KEYS: List[Dict[str, List[int]]] = [
    {
        # Key used by GAN Gen2, Gen3 and Gen4 cubes
        "key": [0x01, 0x02, 0x42, 0x28, 0x31, 0x91, 0x16, 0x07, 
                0x20, 0x05, 0x18, 0x54, 0x42, 0x11, 0x12, 0x53],
        "iv": [0x11, 0x03, 0x32, 0x28, 0x21, 0x01, 0x76, 0x27,
               0x20, 0x95, 0x78, 0x14, 0x32, 0x12, 0x02, 0x43]
    },
    {
        # Key used by MoYu AI 2023
        "key": [0x05, 0x12, 0x02, 0x45, 0x02, 0x01, 0x29, 0x56,
                0x12, 0x78, 0x12, 0x76, 0x81, 0x01, 0x08, 0x03],
        "iv": [0x01, 0x44, 0x28, 0x06, 0x86, 0x21, 0x22, 0x28,
               0x51, 0x05, 0x08, 0x31, 0x82, 0x02, 0x21, 0x06]
    }
]

# Timer-specific constants
GAN_TIMER_SERVICE = "0000fff0-0000-1000-8000-00805f9b34fb"
GAN_TIMER_CHARACTERISTIC = "0000fff1-0000-1000-8000-00805f9b34fb"

# Common manufacturer IDs
GAN_MANUFACTURER_ID = 0x4D43  # "MC" in hex


def extract_mac_from_manufacturer_data(manufacturer_data: Dict[int, bytes]) -> str:
    """
    Extract MAC address from manufacturer data using GAN CIC list.
    
    Args:
        manufacturer_data: Dictionary of manufacturer ID to data bytes
        
    Returns:
        MAC address string in format "XX:XX:XX:XX:XX:XX" or empty string if not found
    """
    mac_bytes = []
    
    # Check all known GAN Company Identifier Codes
    for cic in GAN_CIC_LIST:
        if cic in manufacturer_data:
            data = manufacturer_data[cic]
            # MAC is in last 6 bytes of first 9 bytes
            if len(data) >= 6:
                # Extract last 6 bytes and reverse order for MAC format
                mac_bytes = list(data[:9])[-6:]
                mac_bytes.reverse()
                break
    
    if mac_bytes:
        # Format as MAC address string
        return ":".join(f"{byte:02X}" for byte in mac_bytes)
    
    return ""


def get_manufacturer_data_bytes(manufacturer_data: Dict[int, bytes]) -> bytes:
    """
    Get manufacturer data bytes for GAN cubes.
    
    Args:
        manufacturer_data: Manufacturer data from advertisement
        
    Returns:
        First 9 bytes of manufacturer data or empty bytes
    """
    for cic in GAN_CIC_LIST:
        if cic in manufacturer_data:
            data = manufacturer_data[cic]
            return data[:9] if len(data) >= 9 else data
    
    return b""