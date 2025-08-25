#!/usr/bin/env python3
"""Test pyee installation and event emitter functionality."""

import sys
print(f"Python version: {sys.version}")

# Test pyee import
try:
    import pyee
    print(f"pyee installed: {pyee.__version__ if hasattr(pyee, '__version__') else 'version unknown'}")
    print(f"pyee module location: {pyee.__file__}")
    
    # Check what's available in pyee
    print(f"pyee attributes: {dir(pyee)}")
    
    # Try to import AsyncEventEmitter
    try:
        from pyee import AsyncEventEmitter
        print("AsyncEventEmitter available")
    except ImportError as e:
        print(f"AsyncEventEmitter not available: {e}")
    
    # Try to import EventEmitter  
    try:
        from pyee import EventEmitter
        print("EventEmitter available")
    except ImportError as e:
        print(f"EventEmitter not available: {e}")
        
except ImportError as e:
    print(f"pyee not installed: {e}")

# Test the actual event emitter being used
print("\n--- Testing actual EventEmitter implementation ---")
from gan_web_bluetooth.event_emitter import EventEmitter

emitter = EventEmitter()
print(f"EventEmitter class: {EventEmitter}")
print(f"EventEmitter instance: {emitter}")
print(f"EventEmitter methods: {[m for m in dir(emitter) if not m.startswith('_')]}")

# Test basic functionality
test_results = []

def test_handler(event):
    test_results.append(f"Received: {event}")

emitter.on('test', test_handler)
emitter.emit('test', 'test_data')

print(f"Test results: {test_results}")

# Test with None
emitter.emit('test', None)
print(f"Test results after None: {test_results}")