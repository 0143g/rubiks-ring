#!/usr/bin/env python3
"""Check pyee EventEmitter internals."""

try:
    from pyee import EventEmitter
    
    print("Creating EventEmitter...")
    ee = EventEmitter()
    
    print(f"EventEmitter attributes: {[x for x in dir(ee) if not x.startswith('__')]}")
    
    # Check if it has _events
    if hasattr(ee, '_events'):
        print(f"Has _events: {type(ee._events)}")
        print(f"_events value: {ee._events}")
    else:
        print("No _events attribute")
        
    # Check what happens when we access events
    print("\nTrying to register a handler...")
    
    def test_handler(data):
        print(f"Handler called with: {data}")
    
    ee.on('test', test_handler)
    
    # Check _events again
    if hasattr(ee, '_events'):
        print(f"After registration, _events: {ee._events}")
        if 'test' in ee._events:
            print(f"test event handlers: {ee._events['test']}")
            
    # Try to emit
    print("\nEmitting event...")
    ee.emit('test', 'hello')
    
except ImportError:
    print("pyee not installed")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()