#!/usr/bin/env python3
"""
Cube Performance Diagnostic - Measure actual Hz/latency from GAN cube
"""

import asyncio
import time
import sys
from pathlib import Path
from collections import deque

sys.path.append(str(Path(__file__).parent.parent))
from gan_web_bluetooth import GanSmartCube
from gan_web_bluetooth.protocols.base import (
    GanCubeMoveEvent, 
    GanCubeOrientationEvent,
    GanCubeBatteryEvent
)


class CubeDiagnostic:
    def __init__(self):
        self.cube = None
        
        # Timing data
        self.orientation_times = deque(maxlen=100)
        self.move_times = deque(maxlen=100)
        self.last_orientation = 0
        self.last_move = 0
        
        # Stats
        self.orientation_count = 0
        self.move_count = 0
        self.start_time = 0
        
        # Latency tracking
        self.orientation_intervals = deque(maxlen=100)
        self.move_intervals = deque(maxlen=100)
    
    def handle_orientation(self, event):
        now = time.perf_counter()
        self.orientation_count += 1
        
        if self.last_orientation > 0:
            interval_ms = (now - self.last_orientation) * 1000
            self.orientation_intervals.append(interval_ms)
        
        self.last_orientation = now
        self.orientation_times.append(now)
    
    def handle_move(self, event):
        now = time.perf_counter()
        print(f"[{now:.3f}] Move: {event.move}")
        self.move_count += 1
        
        if self.last_move > 0:
            interval_ms = (now - self.last_move) * 1000
            self.move_intervals.append(interval_ms)
            print(f"  Interval since last move: {interval_ms:.1f}ms")
        
        self.last_move = now
        self.move_times.append(now)
    
    def handle_battery(self, event):
        print(f"Battery: {event.level}%")
    
    def print_stats(self):
        if not self.start_time:
            return
        
        runtime = time.perf_counter() - self.start_time
        
        print("\n" + "="*50)
        print(f"Runtime: {runtime:.1f} seconds")
        print("="*50)
        
        # Orientation stats
        if len(self.orientation_intervals) > 10:
            avg_interval = sum(self.orientation_intervals) / len(self.orientation_intervals)
            min_interval = min(self.orientation_intervals)
            max_interval = max(self.orientation_intervals)
            hz = 1000 / avg_interval if avg_interval > 0 else 0
            
            print(f"\nORIENTATION DATA:")
            print(f"  Total events: {self.orientation_count}")
            print(f"  Average Hz: {hz:.1f}")
            print(f"  Average interval: {avg_interval:.1f}ms")
            print(f"  Min interval: {min_interval:.1f}ms")
            print(f"  Max interval: {max_interval:.1f}ms")
            
            # Check for gaps
            gaps = [i for i in self.orientation_intervals if i > 100]
            if gaps:
                print(f"  ⚠️  Gaps >100ms: {len(gaps)} times")
                print(f"      Longest gap: {max(gaps):.1f}ms")
        else:
            print(f"\nORIENTATION: {self.orientation_count} events (not enough data)")
        
        # Move stats
        if self.move_count > 0:
            print(f"\nMOVE DATA:")
            print(f"  Total moves: {self.move_count}")
            if len(self.move_intervals) > 0:
                avg_move_interval = sum(self.move_intervals) / len(self.move_intervals)
                print(f"  Average interval: {avg_move_interval:.1f}ms")
        
        print("="*50)
    
    async def connect(self):
        self.cube = GanSmartCube()
        
        self.cube.on('orientation', self.handle_orientation)
        self.cube.on('move', self.handle_move)
        self.cube.on('battery', self.handle_battery)
        
        await self.cube.connect()
        print("Connected to cube!")
        self.start_time = time.perf_counter()
    
    async def run(self):
        await self.connect()
        
        print("\n" + "="*50)
        print("CUBE DIAGNOSTIC RUNNING")
        print("Rotate the cube continuously to test orientation")
        print("Make some moves to test move detection")
        print("Press Ctrl+C to see final stats")
        print("="*50 + "\n")
        
        try:
            while True:
                await asyncio.sleep(5)
                self.print_stats()
        except KeyboardInterrupt:
            print("\n\nFINAL STATS:")
            self.print_stats()


async def main():
    diagnostic = CubeDiagnostic()
    await diagnostic.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nDiagnostic complete")
