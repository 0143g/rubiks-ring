#!/usr/bin/env python3
"""Test if pyee is causing the slice error."""

import sys
print(f"Python version: {sys.version}")

# First, check what version of pyee we're using
try:
    import pyee
    print(f"\npyee imported successfully")
    print(f"pyee location: {pyee.__file__}")
    print(f"pyee attributes: {[x for x in dir(pyee) if not x.startswith('_')]}")
    
    # Check if we have EventEmitter
    if hasattr(pyee, 'EventEmitter'):
        print("Has EventEmitter")
        from pyee import EventEmitter
        
        # Test basic usage
        class TestClass:
            def __init__(self):
                self.emitter = EventEmitter()
                
            def setup(self):
                # Register handler - this might be where the issue is
                self.emitter.on('test', self.handle_test)
                
            def handle_test(self, data):
                print(f"Handler got: {data}")
                
        print("\nTesting EventEmitter...")
        test = TestClass()
        test.setup()
        
        # Try emitting
        print("Emitting with None...")
        test.emitter.emit('test', None)
        
        print("Emitting with slice object...")
        test.emitter.emit('test', slice(None, None, None))
        
    # Check if we have AsyncEventEmitter
    if hasattr(pyee, 'AsyncEventEmitter'):
        print("\nHas AsyncEventEmitter")
        
except ImportError as e:
    print(f"pyee not available: {e}")
except Exception as e:
    print(f"Error testing pyee: {e}")
    print(f"Error type: {type(e)}")
    import traceback
    traceback.print_exc()

# Now test our event emitter wrapper
print("\n" + "="*50)
print("Testing our EventEmitter wrapper...")
from gan_web_bluetooth.event_emitter import EventEmitter

class TestDashboard:
    def __init__(self):
        self.emitter = EventEmitter()
        
    def setup(self):
        self.emitter.on('connected', self.handle_connected)
        
    def handle_connected(self, event_data):
        print(f"Connected handler got: {event_data}, type: {type(event_data)}")
        
    def test_emit(self):
        print("Emitting 'connected' with None...")
        self.emitter.emit('connected', None)

try:
    dashboard = TestDashboard()
    dashboard.setup()
    dashboard.test_emit()
    print("Success!")
except Exception as e:
    print(f"Error: {e}")
    print(f"Error type: {type(e)}")
    import traceback
    traceback.print_exc()