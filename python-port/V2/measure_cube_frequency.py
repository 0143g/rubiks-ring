#!/usr/bin/env python3
"""
Measure the actual frequency of data from the GAN cube.
This helps us understand the real constraints for V2 implementation.
"""

import asyncio
import time
import sys
from collections import defaultdict, deque
from pathlib import Path

# Add parent directory to path to import gan_web_bluetooth
sys.path.append(str(Path(__file__).parent.parent))

from gan_web_bluetooth import GanSmartCube
from gan_web_bluetooth.utils import now

class CubeFrequencyAnalyzer:
    def __init__(self):
        self.cube = None
        self.event_times = defaultdict(lambda: deque(maxlen=100))
        self.event_counts = defaultdict(int)
        self.start_time = None
        self.last_report = 0
        
        # Track inter-arrival times
        self.last_event_time = defaultdict(float)
        self.inter_arrival_times = defaultdict(lambda: deque(maxlen=100))
        
        # Track duplicate moves
        self.last_move = None
        self.last_move_time = 0
        self.duplicate_moves = 0
        
    async def connect(self):
        """Connect to the cube and setup event handlers."""
        print("Scanning for GAN cube...")
        self.cube = GanSmartCube()
        
        # Setup event handlers
        self.cube.on('move', self.on_move)
        self.cube.on('orientation', self.on_orientation)
        self.cube.on('facelets', self.on_facelets)
        self.cube.on('battery', self.on_battery)
        
        await self.cube.connect()
        print("Connected! Starting frequency measurement...")
        print("Move the cube around to generate orientation data.")
        print("Turn faces to generate move events.\n")
        self.start_time = time.perf_counter()
        
    def record_event(self, event_type: str):
        """Record an event and calculate timing statistics."""
        current_time = time.perf_counter()
        
        # Record event
        self.event_times[event_type].append(current_time)
        self.event_counts[event_type] += 1
        
        # Calculate inter-arrival time
        if event_type in self.last_event_time:
            inter_arrival = (current_time - self.last_event_time[event_type]) * 1000  # ms
            self.inter_arrival_times[event_type].append(inter_arrival)
        
        self.last_event_time[event_type] = current_time
        
    def on_move(self, event):
        """Handle move events."""
        self.record_event('move')
        
        # Check for duplicates
        current_time = time.perf_counter() * 1000  # ms
        if event.move == self.last_move and (current_time - self.last_move_time) < 100:
            self.duplicate_moves += 1
            print(f"  ⚠️ Duplicate move: {event.move} ({current_time - self.last_move_time:.1f}ms apart)")
        
        self.last_move = event.move
        self.last_move_time = current_time
        
    def on_orientation(self, event):
        """Handle orientation events."""
        self.record_event('orientation')
        
    def on_facelets(self, event):
        """Handle facelet state events."""
        self.record_event('facelets')
        
    def on_battery(self, event):
        """Handle battery events."""
        self.record_event('battery')
        
    def calculate_frequency(self, event_type: str) -> tuple:
        """Calculate frequency statistics for an event type."""
        times = self.event_times[event_type]
        if len(times) < 2:
            return 0, 0, 0, 0
        
        # Calculate actual frequency from first to last event
        duration = times[-1] - times[0]
        if duration == 0:
            return 0, 0, 0, 0
            
        frequency = (len(times) - 1) / duration
        
        # Calculate inter-arrival statistics
        inter_arrivals = list(self.inter_arrival_times[event_type])
        if not inter_arrivals:
            return frequency, 0, 0, 0
            
        avg_interval = sum(inter_arrivals) / len(inter_arrivals)
        min_interval = min(inter_arrivals)
        max_interval = max(inter_arrivals)
        
        return frequency, avg_interval, min_interval, max_interval
        
    async def print_report(self):
        """Print frequency analysis report."""
        while True:
            await asyncio.sleep(2)  # Report every 2 seconds
            
            if not self.start_time:
                continue
                
            runtime = time.perf_counter() - self.start_time
            print("\n" + "="*60)
            print(f"Runtime: {runtime:.1f}s")
            print("="*60)
            
            for event_type in ['orientation', 'move', 'facelets', 'battery']:
                count = self.event_counts[event_type]
                if count == 0:
                    continue
                    
                freq, avg_interval, min_interval, max_interval = self.calculate_frequency(event_type)
                
                print(f"\n{event_type.upper()}:")
                print(f"  Count: {count}")
                print(f"  Frequency: {freq:.1f} Hz")
                print(f"  Avg interval: {avg_interval:.1f}ms")
                print(f"  Min interval: {min_interval:.1f}ms")
                print(f"  Max interval: {max_interval:.1f}ms")
                
                if event_type == 'move' and self.duplicate_moves > 0:
                    print(f"  Duplicate moves: {self.duplicate_moves}")
            
            # Show Bluetooth constraints
            print("\n" + "-"*60)
            print("BLE CONSTRAINTS:")
            print(f"  Theoretical min latency: 7.5ms (BLE connection interval)")
            print(f"  Typical BLE latency: 15-30ms")
            print(f"  Observed orientation rate: ~{self.calculate_frequency('orientation')[0]:.1f}Hz")
            
            # Processing recommendations
            orientation_freq = self.calculate_frequency('orientation')[0]
            if orientation_freq > 0:
                print("\nRECOMMENDATIONS:")
                print(f"  Orientation updates every ~{1000/orientation_freq:.0f}ms")
                print(f"  Gamepad update rate: 60-125Hz (8-16ms)")
                print(f"  Expected total latency: {1000/orientation_freq + 10:.0f}-{1000/orientation_freq + 30:.0f}ms")
                
    async def run(self):
        """Main run loop."""
        try:
            await self.connect()
            
            # Start report task
            report_task = asyncio.create_task(self.print_report())
            
            # Run for 30 seconds
            print("Measuring for 30 seconds. Move the cube to generate data...")
            await asyncio.sleep(30)
            
            # Final report
            print("\n" + "="*60)
            print("FINAL REPORT")
            print("="*60)
            
            runtime = time.perf_counter() - self.start_time
            
            for event_type in ['orientation', 'move']:
                count = self.event_counts[event_type]
                if count == 0:
                    continue
                    
                freq, avg_interval, min_interval, max_interval = self.calculate_frequency(event_type)
                
                print(f"\n{event_type.upper()} SUMMARY:")
                print(f"  Total events: {count}")
                print(f"  Average frequency: {freq:.1f} Hz")
                print(f"  Average interval: {avg_interval:.1f}ms")
                print(f"  Min/Max interval: {min_interval:.1f}ms / {max_interval:.1f}ms")
                
                # Show distribution
                intervals = list(self.inter_arrival_times[event_type])
                if intervals:
                    intervals.sort()
                    p50 = intervals[len(intervals)//2]
                    p90 = intervals[int(len(intervals)*0.9)]
                    p99 = intervals[int(len(intervals)*0.99)] if len(intervals) > 100 else max_interval
                    print(f"  Interval percentiles: P50={p50:.1f}ms, P90={p90:.1f}ms, P99={p99:.1f}ms")
            
            print("\nV2 REALISTIC TARGETS:")
            orientation_freq = self.calculate_frequency('orientation')[0]
            if orientation_freq > 0:
                base_latency = 1000/orientation_freq
                print(f"  Base cube latency: ~{base_latency:.0f}ms")
                print(f"  Processing overhead target: <10ms")
                print(f"  Total average latency: {base_latency + 5:.0f}-{base_latency + 10:.0f}ms")
                print(f"  Total max latency: <100ms (BLE hiccups)")
                
        except KeyboardInterrupt:
            print("\nMeasurement interrupted")
        finally:
            if self.cube:
                await self.cube.disconnect()
            print("Disconnected")

async def main():
    analyzer = CubeFrequencyAnalyzer()
    await analyzer.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown")