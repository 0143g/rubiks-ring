"""Platform-specific utilities and compatibility helpers."""

import sys
import platform
import subprocess
from typing import Optional


def is_wsl() -> bool:
    """Check if running in Windows Subsystem for Linux."""
    try:
        with open('/proc/version', 'r') as f:
            return 'microsoft' in f.read().lower()
    except FileNotFoundError:
        return False


def is_bluetooth_available() -> bool:
    """Check if Bluetooth is available on this platform."""
    if is_wsl():
        return False
    
    # Check if BlueZ is available on Linux
    if platform.system() == 'Linux':
        try:
            result = subprocess.run(['hciconfig'], capture_output=True, text=True)
            return result.returncode == 0
        except FileNotFoundError:
            return False
    
    # On Windows and macOS, assume Bluetooth is available
    return True


def get_platform_info() -> dict:
    """Get platform information for debugging."""
    return {
        'system': platform.system(),
        'release': platform.release(),
        'version': platform.version(),
        'machine': platform.machine(),
        'processor': platform.processor(),
        'is_wsl': is_wsl(),
        'bluetooth_available': is_bluetooth_available(),
        'python_version': sys.version
    }


def print_bluetooth_help():
    """Print help for Bluetooth setup on different platforms."""
    print("\n🔧 BLUETOOTH SETUP HELP")
    print("=" * 50)
    
    if is_wsl():
        print("❌ WSL (Windows Subsystem for Linux) Detected")
        print("\nWSL doesn't have direct access to Bluetooth hardware.")
        print("To use Bluetooth with this library, you have several options:")
        print("\n1. 📱 Use Windows natively:")
        print("   - Install Python on Windows directly")
        print("   - Run the script from Windows Command Prompt or PowerShell")
        print("\n2. 🐳 Use WSL with USB passthrough (advanced):")
        print("   - Enable WSL USB support (requires Windows 11)")
        print("   - Use usbipd to attach Bluetooth adapter")
        print("\n3. 🌐 Use a Bluetooth bridge:")
        print("   - Run a Bluetooth proxy on Windows")
        print("   - Connect to it from WSL over network")
        print("\n4. 💻 Use a native Linux machine:")
        print("   - Run on a real Linux system with Bluetooth")
        
    elif platform.system() == 'Linux':
        print("🐧 Linux Detected")
        print("\nTo enable Bluetooth on Linux:")
        print("1. Install BlueZ: sudo apt install bluez")
        print("2. Start Bluetooth service: sudo systemctl start bluetooth")
        print("3. Enable Bluetooth: sudo systemctl enable bluetooth")
        print("4. Add user to bluetooth group: sudo usermod -a -G bluetooth $USER")
        print("5. Restart your session or run: newgrp bluetooth")
        
    elif platform.system() == 'Darwin':
        print("🍎 macOS Detected")
        print("\nBluetooth should work out of the box on macOS.")
        print("Make sure Bluetooth is enabled in System Preferences.")
        
    elif platform.system() == 'Windows':
        print("🪟 Windows Detected")
        print("\nBluetooth should work with the winrt backend.")
        print("Make sure Bluetooth is enabled in Windows Settings.")
    
    print("\n📚 Additional Resources:")
    print("- Bleak documentation: https://bleak.readthedocs.io/")
    print("- Platform support: https://bleak.readthedocs.io/en/latest/platform-support.html")


class MockBleakScanner:
    """Mock scanner for platforms without Bluetooth."""
    
    @staticmethod
    async def find_device_by_filter(*args, **kwargs):
        """Mock device finder that explains the issue."""
        print_bluetooth_help()
        raise RuntimeError(
            "Bluetooth not available on this platform. "
            "See help above for setup instructions."
        )


class MockBleakClient:
    """Mock client for platforms without Bluetooth."""
    
    def __init__(self, address):
        self.address = address
    
    async def connect(self):
        print_bluetooth_help()
        raise RuntimeError(
            "Bluetooth not available on this platform. "
            "See help above for setup instructions."
        )
    
    async def disconnect(self):
        pass
    
    async def get_services(self):
        return []