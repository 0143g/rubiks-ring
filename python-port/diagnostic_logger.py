#!/usr/bin/env python3
"""
Diagnostic Logger for Cube Dashboard Performance Analysis
Tracks various metrics to identify performance bottlenecks and memory leaks
"""

import os
import time
import json
import psutil
import asyncio
import threading
from datetime import datetime
from typing import Dict, Any, Optional
from collections import deque
import traceback

class DiagnosticLogger:
    def __init__(self, log_dir: str = "diagnostic_logs"):
        """Initialize the diagnostic logger."""
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        
        # Create timestamped log file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(log_dir, f"dashboard_diagnostics_{timestamp}.jsonl")
        self.metrics_file = os.path.join(log_dir, f"dashboard_metrics_{timestamp}.csv")
        
        # Performance tracking
        self.start_time = time.time()
        self.message_counts = {
            'orientation': 0,
            'moves': 0,
            'controller_bridge': 0,
            'websocket_send': 0,
            'websocket_receive': 0,
            'bluetooth_receive': 0,
            'socketio_emit': 0
        }
        
        # Timing metrics
        self.timing_buffers = {
            'orientation_processing': deque(maxlen=100),
            'move_processing': deque(maxlen=100),
            'bridge_send': deque(maxlen=100),
            'socketio_emit': deque(maxlen=100),
            'bluetooth_read': deque(maxlen=100)
        }
        
        # Queue sizes
        self.queue_sizes = {
            'pending_messages': 0,
            'socketio_queue': 0,
            'bridge_queue': 0
        }
        
        # Memory tracking
        self.process = psutil.Process()
        self.initial_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        self.memory_samples = deque(maxlen=60)  # Keep last 60 samples
        
        # Event loop monitoring
        self.loop_blocked_times = deque(maxlen=100)
        self.last_loop_check = time.time()
        
        # Error tracking
        self.error_counts = {}
        
        # Write CSV header
        with open(self.metrics_file, 'w') as f:
            f.write("timestamp,uptime_sec,memory_mb,memory_delta_mb,cpu_percent,")
            f.write("msg_orientation,msg_moves,msg_controller,msg_ws_send,msg_ws_recv,msg_bt_recv,msg_socketio,")
            f.write("avg_orientation_ms,avg_move_ms,avg_bridge_ms,avg_socketio_ms,avg_bt_read_ms,")
            f.write("queue_pending,queue_socketio,queue_bridge,")
            f.write("loop_blocked_ms,error_count\n")
        
        # Start background monitoring thread
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        self.log_event("system", "Diagnostic logging initialized", {
            "log_file": self.log_file,
            "metrics_file": self.metrics_file
        })
    
    def log_event(self, category: str, event: str, data: Optional[Dict] = None, 
                  error: Optional[Exception] = None):
        """Log an event with optional data and error information."""
        try:
            log_entry = {
                'timestamp': time.time(),
                'uptime': time.time() - self.start_time,
                'category': category,
                'event': event,
                'data': data or {}
            }
            
            if error:
                log_entry['error'] = {
                    'type': type(error).__name__,
                    'message': str(error),
                    'traceback': traceback.format_exc()
                }
                
                # Track error counts
                error_key = f"{category}:{type(error).__name__}"
                self.error_counts[error_key] = self.error_counts.get(error_key, 0) + 1
            
            # Write to JSONL file
            with open(self.log_file, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception as e:
            print(f"Failed to log event: {e}")
    
    def track_message(self, msg_type: str):
        """Track message counts."""
        if msg_type in self.message_counts:
            self.message_counts[msg_type] += 1
    
    def track_timing(self, operation: str, duration_ms: float):
        """Track operation timing."""
        if operation in self.timing_buffers:
            self.timing_buffers[operation].append(duration_ms)
            
            # Log if operation is unusually slow
            if duration_ms > 100:  # More than 100ms is concerning
                self.log_event("performance", f"Slow {operation}", {
                    'duration_ms': duration_ms
                })
    
    def update_queue_size(self, queue_name: str, size: int):
        """Update queue size tracking."""
        self.queue_sizes[queue_name] = size
        
        # Log if queue is building up
        if size > 50:  # More than 50 items queued is concerning
            self.log_event("performance", f"Queue buildup: {queue_name}", {
                'queue_size': size
            })
    
    def check_event_loop_responsiveness(self):
        """Check if event loop is responsive."""
        current_time = time.time()
        blocked_time = (current_time - self.last_loop_check) * 1000  # ms
        self.last_loop_check = current_time
        
        if blocked_time > 50:  # More than 50ms between checks indicates blocking
            self.loop_blocked_times.append(blocked_time)
            self.log_event("performance", "Event loop blocked", {
                'blocked_ms': blocked_time
            })
        
        return blocked_time
    
    def _monitor_loop(self):
        """Background thread to periodically collect system metrics."""
        while self.monitoring:
            try:
                # Collect metrics
                memory_info = self.process.memory_info()
                memory_mb = memory_info.rss / 1024 / 1024
                memory_delta = memory_mb - self.initial_memory
                cpu_percent = self.process.cpu_percent()
                
                self.memory_samples.append(memory_mb)
                
                # Check for memory leak
                if len(self.memory_samples) >= 10:
                    recent_avg = sum(list(self.memory_samples)[-10:]) / 10
                    if recent_avg > self.initial_memory + 100:  # 100MB increase
                        self.log_event("performance", "Possible memory leak detected", {
                            'initial_mb': self.initial_memory,
                            'current_mb': memory_mb,
                            'increase_mb': memory_delta
                        })
                
                # Calculate averages
                def safe_avg(buffer):
                    return sum(buffer) / len(buffer) if buffer else 0
                
                # Write metrics to CSV
                metrics_row = [
                    datetime.now().isoformat(),
                    f"{time.time() - self.start_time:.1f}",
                    f"{memory_mb:.1f}",
                    f"{memory_delta:.1f}",
                    f"{cpu_percent:.1f}",
                    *[str(self.message_counts.get(k, 0)) for k in [
                        'orientation', 'moves', 'controller_bridge', 
                        'websocket_send', 'websocket_receive', 'bluetooth_receive', 'socketio_emit'
                    ]],
                    *[f"{safe_avg(self.timing_buffers.get(k, [])):.1f}" for k in [
                        'orientation_processing', 'move_processing', 'bridge_send', 
                        'socketio_emit', 'bluetooth_read'
                    ]],
                    *[str(self.queue_sizes.get(k, 0)) for k in [
                        'pending_messages', 'socketio_queue', 'bridge_queue'
                    ]],
                    f"{safe_avg(self.loop_blocked_times):.1f}",
                    str(sum(self.error_counts.values()))
                ]
                
                with open(self.metrics_file, 'a') as f:
                    f.write(','.join(metrics_row) + '\n')
                
                # Log summary every 30 seconds
                if int(time.time() - self.start_time) % 30 == 0:
                    self.log_event("metrics", "Periodic summary", {
                        'memory_mb': memory_mb,
                        'memory_delta_mb': memory_delta,
                        'cpu_percent': cpu_percent,
                        'message_counts': dict(self.message_counts),
                        'avg_timings_ms': {k: safe_avg(v) for k, v in self.timing_buffers.items()},
                        'queue_sizes': dict(self.queue_sizes),
                        'error_counts': dict(self.error_counts)
                    })
                
            except Exception as e:
                print(f"Monitor loop error: {e}")
            
            time.sleep(1)  # Collect metrics every second
    
    def shutdown(self):
        """Shutdown the diagnostic logger."""
        self.monitoring = False
        self.monitor_thread.join(timeout=2)
        
        # Final summary
        self.log_event("system", "Diagnostic logging shutdown", {
            'total_uptime': time.time() - self.start_time,
            'final_memory_mb': self.process.memory_info().rss / 1024 / 1024,
            'total_messages': dict(self.message_counts),
            'total_errors': dict(self.error_counts)
        })
        
        print(f"Diagnostic logs saved to: {self.log_file}")
        print(f"Metrics CSV saved to: {self.metrics_file}")


class AsyncDiagnosticHelper:
    """Helper class for async timing operations."""
    
    def __init__(self, logger: DiagnosticLogger):
        self.logger = logger
    
    async def timed_operation(self, operation: str, coro):
        """Execute a coroutine and track its timing."""
        start = time.time()
        try:
            result = await coro
            duration_ms = (time.time() - start) * 1000
            self.logger.track_timing(operation, duration_ms)
            return result
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            self.logger.track_timing(operation, duration_ms)
            self.logger.log_event(operation, "Operation failed", error=e)
            raise