"""Event emitter implementation compatible with different pyee versions."""

import asyncio
from typing import Callable, Dict, List, Any
from collections import defaultdict

try:
    # Try the newer pyee version first
    from pyee import AsyncEventEmitter as PyeeAsyncEventEmitter
    
    class EventEmitter(PyeeAsyncEventEmitter):
        """Wrapper for pyee AsyncEventEmitter."""
        pass

except ImportError:
    try:
        # Try older pyee version
        from pyee import EventEmitter as PyeeEventEmitter
        
        class EventEmitter(PyeeEventEmitter):
            """Wrapper for pyee EventEmitter with async support."""
            
            def emit(self, event: str, *args, **kwargs):
                """Emit event, handling both sync and async handlers."""
                if event in self._events:
                    for handler in self._events[event][:]:  # Copy to avoid modification during iteration
                        try:
                            if asyncio.iscoroutinefunction(handler):
                                # Schedule async handler
                                asyncio.create_task(handler(*args, **kwargs))
                            else:
                                # Call sync handler directly
                                handler(*args, **kwargs)
                        except Exception as e:
                            # Don't let handler errors break the emitter
                            print(f"Event handler error: {e}")
                            
    except ImportError:
        # Fallback to custom implementation if pyee not available
        class EventEmitter:
            """Simple event emitter implementation."""
            
            def __init__(self):
                self._events: Dict[str, List[Callable]] = defaultdict(list)
            
            def on(self, event: str, handler: Callable):
                """Register event handler."""
                self._events[event].append(handler)
            
            def off(self, event: str, handler: Callable = None):
                """Unregister event handler."""
                if handler:
                    if handler in self._events[event]:
                        self._events[event].remove(handler)
                else:
                    self._events[event].clear()
            
            def remove_listener(self, event: str, handler: Callable):
                """Remove specific listener (alias for off)."""
                self.off(event, handler)
            
            def remove_all_listeners(self, event: str):
                """Remove all listeners for event."""
                self._events[event].clear()
            
            def emit(self, event: str, *args, **kwargs):
                """Emit event to all registered handlers."""
                if event in self._events:
                    for handler in self._events[event][:]:  # Copy to avoid modification during iteration
                        try:
                            if asyncio.iscoroutinefunction(handler):
                                # Schedule async handler
                                asyncio.create_task(handler(*args, **kwargs))
                            else:
                                # Call sync handler directly
                                handler(*args, **kwargs)
                        except Exception as e:
                            # Don't let handler errors break the emitter
                            print(f"Event handler error: {e}")