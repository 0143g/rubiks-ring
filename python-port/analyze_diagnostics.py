#!/usr/bin/env python3
"""
Analyze diagnostic logs to identify performance issues
"""

import json
import sys
import os
from pathlib import Path
import statistics
import csv
from datetime import datetime

def analyze_jsonl_log(log_file):
    """Analyze the JSON Lines log file."""
    print(f"\n=== Analyzing {log_file} ===\n")
    
    events = []
    errors = []
    slow_operations = []
    memory_warnings = []
    
    with open(log_file, 'r') as f:
        for line in f:
            try:
                event = json.loads(line)
                events.append(event)
                
                # Collect errors
                if 'error' in event:
                    errors.append(event)
                
                # Check for slow operations
                if event.get('category') == 'performance':
                    if 'slow' in event.get('event', '').lower():
                        slow_operations.append(event)
                    if 'memory' in event.get('event', '').lower():
                        memory_warnings.append(event)
                        
            except json.JSONDecodeError:
                print(f"Failed to parse line: {line[:100]}...")
    
    print(f"Total events logged: {len(events)}")
    print(f"Total errors: {len(errors)}")
    print(f"Slow operations detected: {len(slow_operations)}")
    print(f"Memory warnings: {len(memory_warnings)}")
    
    # Analyze errors
    if errors:
        print("\n--- Top Errors ---")
        error_types = {}
        for error in errors:
            error_type = error.get('error', {}).get('type', 'Unknown')
            error_types[error_type] = error_types.get(error_type, 0) + 1
        
        for error_type, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  {error_type}: {count} occurrences")
    
    # Analyze slow operations
    if slow_operations:
        print("\n--- Slow Operations ---")
        for op in slow_operations[:5]:
            duration = op.get('data', {}).get('duration_ms', 0)
            print(f"  {op.get('event')}: {duration:.1f}ms at {op.get('uptime', 0):.1f}s")
    
    # Check for event loop blocking
    loop_blocks = [e for e in events if 'loop blocked' in e.get('event', '').lower()]
    if loop_blocks:
        print(f"\n--- Event Loop Blocking ---")
        print(f"  Total blocks detected: {len(loop_blocks)}")
        block_times = [e.get('data', {}).get('blocked_ms', 0) for e in loop_blocks]
        if block_times:
            print(f"  Max block time: {max(block_times):.1f}ms")
            print(f"  Average block time: {statistics.mean(block_times):.1f}ms")

def analyze_metrics_csv(csv_file):
    """Analyze the metrics CSV file."""
    print(f"\n=== Analyzing {csv_file} ===\n")
    
    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    if not rows:
        print("No metrics data found")
        return
    
    # Memory analysis
    memory_values = [float(row['memory_mb']) for row in rows if row['memory_mb']]
    memory_deltas = [float(row['memory_delta_mb']) for row in rows if row['memory_delta_mb']]
    
    if memory_values:
        print("--- Memory Usage ---")
        print(f"  Initial: {memory_values[0]:.1f} MB")
        print(f"  Final: {memory_values[-1]:.1f} MB")
        print(f"  Peak: {max(memory_values):.1f} MB")
        print(f"  Total increase: {memory_deltas[-1] if memory_deltas else 0:.1f} MB")
        
        # Check for memory leak
        if len(memory_values) > 10:
            # Compare first 10% with last 10%
            first_10pct = memory_values[:len(memory_values)//10]
            last_10pct = memory_values[-len(memory_values)//10:]
            if first_10pct and last_10pct:
                avg_start = statistics.mean(first_10pct)
                avg_end = statistics.mean(last_10pct)
                increase_rate = (avg_end - avg_start) / len(memory_values) * 60  # MB per minute
                if increase_rate > 1:
                    print(f"  ⚠️  POSSIBLE MEMORY LEAK: {increase_rate:.2f} MB/minute growth rate")
    
    # Message throughput analysis
    print("\n--- Message Throughput ---")
    message_types = ['msg_orientation', 'msg_moves', 'msg_controller', 'msg_socketio']
    
    for msg_type in message_types:
        if msg_type in rows[-1]:
            final_count = int(rows[-1][msg_type] or 0)
            runtime = float(rows[-1]['uptime_sec'])
            if runtime > 0:
                rate = final_count / runtime
                print(f"  {msg_type[4:]}: {final_count} total, {rate:.1f}/sec")
    
    # Performance timing analysis
    print("\n--- Average Processing Times ---")
    timing_fields = ['avg_orientation_ms', 'avg_move_ms', 'avg_bridge_ms', 'avg_socketio_ms']
    
    for field in timing_fields:
        if field in rows[-1]:
            values = [float(row[field]) for row in rows if row[field] and float(row[field]) > 0]
            if values:
                avg_time = statistics.mean(values)
                max_time = max(values)
                print(f"  {field[4:-3]}: avg={avg_time:.1f}ms, max={max_time:.1f}ms")
                if avg_time > 50:
                    print(f"    ⚠️  HIGH LATENCY DETECTED")
    
    # Queue buildup analysis
    print("\n--- Queue Sizes ---")
    queue_fields = ['queue_pending', 'queue_socketio', 'queue_bridge']
    
    for field in queue_fields:
        if field in rows[-1]:
            values = [int(row[field]) for row in rows if row[field]]
            if values and any(v > 0 for v in values):
                max_queue = max(values)
                avg_queue = statistics.mean(values)
                print(f"  {field[6:]}: avg={avg_queue:.1f}, max={max_queue}")
                if max_queue > 50:
                    print(f"    ⚠️  QUEUE BUILDUP DETECTED")
    
    # Check for performance degradation over time
    print("\n--- Performance Degradation Check ---")
    
    # Split data into quarters
    quarter_size = len(rows) // 4
    if quarter_size > 0:
        quarters = [
            rows[:quarter_size],
            rows[quarter_size:quarter_size*2],
            rows[quarter_size*2:quarter_size*3],
            rows[quarter_size*3:]
        ]
        
        for timing_field in ['avg_orientation_ms', 'avg_move_ms']:
            if timing_field in rows[0]:
                quarter_avgs = []
                for i, quarter in enumerate(quarters):
                    values = [float(row[timing_field]) for row in quarter 
                             if row[timing_field] and float(row[timing_field]) > 0]
                    if values:
                        quarter_avgs.append(statistics.mean(values))
                
                if len(quarter_avgs) == 4:
                    print(f"\n  {timing_field[4:-3]} by quarter:")
                    for i, avg in enumerate(quarter_avgs):
                        print(f"    Q{i+1}: {avg:.1f}ms")
                    
                    # Check for degradation
                    if quarter_avgs[-1] > quarter_avgs[0] * 1.5:
                        degradation = (quarter_avgs[-1] / quarter_avgs[0] - 1) * 100
                        print(f"    ⚠️  PERFORMANCE DEGRADATION: {degradation:.0f}% slower")

def main():
    """Main entry point."""
    # Find the most recent diagnostic files
    log_dir = Path("diagnostic_logs")
    if not log_dir.exists():
        print("No diagnostic_logs directory found. Run the dashboard first to generate logs.")
        return
    
    # Find most recent files
    jsonl_files = sorted(log_dir.glob("dashboard_diagnostics_*.jsonl"))
    csv_files = sorted(log_dir.glob("dashboard_metrics_*.csv"))
    
    if not jsonl_files and not csv_files:
        print("No diagnostic files found in diagnostic_logs/")
        return
    
    # Analyze the most recent files
    if jsonl_files:
        latest_jsonl = jsonl_files[-1]
        analyze_jsonl_log(latest_jsonl)
    
    if csv_files:
        latest_csv = csv_files[-1]
        analyze_metrics_csv(latest_csv)
    
    print("\n" + "="*50)
    print("ANALYSIS COMPLETE")
    print("="*50)
    
    print("\n📊 Next steps:")
    print("1. If you see memory leaks, check for unclosed resources")
    print("2. If you see queue buildup, the event loop may be blocked")
    print("3. If you see performance degradation, check for accumulating data structures")
    print("4. High latency in socketio_emit could indicate browser/network issues")
    print("5. High latency in bridge_send could indicate controller bridge issues")

if __name__ == "__main__":
    main()