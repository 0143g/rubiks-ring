#!/usr/bin/env python3
"""Test to reproduce the slice error."""

import sys
import asyncio

# Test what happens with underscore
def test_underscore(_):
    print(f"Received: {_}")
    print(f"Type: {type(_)}")

# Call with None
test_underscore(None)

# Test with slice
try:
    # This is what [:] evaluates to
    s = slice(None, None, None)
    print(f"\nSlice object: {s}")
    print(f"Slice as string: {str(s)}")
    
    # What happens if we raise it as an exception?
    raise s
except Exception as e:
    print(f"Exception caught: {e}")
    print(f"Exception type: {type(e)}")

# Now test the actual event emitter
print("\n--- Testing EventEmitter ---")
from gan_web_bluetooth.event_emitter import EventEmitter

class TestClass:
    def __init__(self):
        self.emitter = EventEmitter()
        
    def setup_handlers(self):
        self.emitter.on('test', self.handle_test)
        
    def handle_test(self, data):
        print(f"Handler received: {data}")
        
    def emit_test(self):
        print("Emitting with None...")
        self.emitter.emit('test', None)

test = TestClass()
test.setup_handlers()
test.emit_test()