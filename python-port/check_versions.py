#!/usr/bin/env python3
"""Check all relevant package versions."""

import sys
import importlib
import subprocess

print("Python and Package Versions:")
print("=" * 50)
print(f"Python: {sys.version}")
print(f"Python executable: {sys.executable}")
print()

packages = [
    'bleak',
    'pyee', 
    'flask',
    'flask_socketio',
    'flask_cors',
    'numpy',
    'asyncio',
    'eventlet',
    'python-socketio',
    'websocket-client'
]

for package in packages:
    try:
        if package == 'asyncio':
            import asyncio
            print(f"{package}: built-in")
        else:
            mod = importlib.import_module(package.replace('-', '_'))
            version = getattr(mod, '__version__', 'unknown')
            print(f"{package}: {version}")
    except ImportError:
        print(f"{package}: NOT INSTALLED")
    except Exception as e:
        print(f"{package}: Error - {e}")

print("\n" + "=" * 50)
print("Pip list output:")
try:
    result = subprocess.run([sys.executable, '-m', 'pip', 'list'], 
                          capture_output=True, text=True)
    print(result.stdout)
except Exception as e:
    print(f"Error running pip list: {e}")

print("\n" + "=" * 50)
print("Checking bleak backend:")
try:
    import bleak
    from bleak.backends.winrt.client import BleakClientWinRT
    print("Bleak WinRT backend is available")
except ImportError as e:
    print(f"Bleak WinRT backend error: {e}")

# Check if winrt is available (required for bleak on Windows)
try:
    import winrt
    print(f"winrt: {winrt.__version__ if hasattr(winrt, '__version__') else 'installed'}")
except ImportError:
    print("winrt: NOT INSTALLED (required for bleak on Windows!)")

try:
    import bleak_winrt
    print(f"bleak-winrt: {bleak_winrt.__version__ if hasattr(bleak_winrt, '__version__') else 'installed'}")
except ImportError:
    print("bleak-winrt: NOT INSTALLED (might be needed)")