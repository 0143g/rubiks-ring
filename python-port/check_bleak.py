#!/usr/bin/env python3
"""Check bleak installation details."""

import subprocess
import sys

# Check pip show bleak
print("Checking bleak installation:")
print("=" * 50)
result = subprocess.run([sys.executable, '-m', 'pip', 'show', 'bleak'], 
                      capture_output=True, text=True)
print(result.stdout)

# Try importing and checking what's available
print("\nChecking bleak imports:")
print("=" * 50)
try:
    import bleak
    print("✓ bleak imported successfully")
    print(f"bleak module location: {bleak.__file__}")
    print(f"bleak attributes: {[x for x in dir(bleak) if not x.startswith('_')]}")
    
    # Check for version in different ways
    for attr in ['__version__', 'VERSION', 'version']:
        if hasattr(bleak, attr):
            print(f"Found version attribute '{attr}': {getattr(bleak, attr)}")
    
    # Try to import the main classes
    from bleak import BleakClient, BleakScanner
    print("✓ BleakClient imported")
    print("✓ BleakScanner imported")
    
    # Check backend
    print("\nChecking bleak backend for Windows:")
    try:
        from bleak.backends.winrt.client import BleakClientWinRT
        print("✓ WinRT backend available")
    except ImportError as e:
        print(f"✗ WinRT backend error: {e}")
        
    # Check winrt module (required for Windows)
    try:
        import winrt
        print("✓ winrt module available")
    except ImportError:
        print("✗ winrt module NOT INSTALLED - this is required for bleak on Windows!")
        print("  Run: pip install bleak[winrt]")
        
    # Check bleak-winrt
    try:
        import bleak_winrt
        print("✓ bleak-winrt module available")
    except ImportError:
        print("✗ bleak-winrt NOT INSTALLED")
        print("  Run: pip install bleak-winrt")
        
except ImportError as e:
    print(f"✗ Failed to import bleak: {e}")
except Exception as e:
    print(f"✗ Unexpected error: {e}")
    import traceback
    traceback.print_exc()