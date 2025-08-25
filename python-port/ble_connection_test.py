#!/usr/bin/env python3
"""
Minimal BLE connection test to diagnose packet delivery issues.
Tests different connection parameters to see if we can get smoother data flow.
"""
import asyncio
import time
from bleak import BleakClient, BleakScanner
from collections import deque

class ConnectionTester:
    def __init__(self):
        self.packet_count = 0
        self.last_time = None
        self.delays = deque(maxlen=100)
        self.slow_packets = 0
        self.fast_packets = 0
        
    def handle_notification(self, sender, data):
        current_time = time.time()
        self.packet_count += 1
        
        if self.last_time:
            delay_ms = (current_time - self.last_time) * 1000
            self.delays.append(delay_ms)
            
            # Categorize delay
            if delay_ms > 100:
                self.slow_packets += 1
                marker = "🔴"
            elif delay_ms < 10:
                self.fast_packets += 1
                marker = "⚡"
            else:
                marker = "✅"
            
            # Only print problematic packets
            if delay_ms > 100 or delay_ms < 10:
                print(f"{marker} Packet #{self.packet_count}: {delay_ms:.1f}ms delay")
        
        self.last_time = current_time
    
    def print_summary(self):
        if self.delays:
            avg_delay = sum(self.delays) / len(self.delays)
            max_delay = max(self.delays)
            min_delay = min(self.delays)
            
            print("\n" + "="*50)
            print(f"📊 Connection Statistics:")
            print(f"   Total packets: {self.packet_count}")
            print(f"   Avg delay: {avg_delay:.1f}ms")
            print(f"   Min delay: {min_delay:.1f}ms")
            print(f"   Max delay: {max_delay:.1f}ms")
            print(f"   🔴 Slow (>100ms): {self.slow_packets} packets")
            print(f"   ⚡ Fast (<10ms): {self.fast_packets} packets")
            print("="*50)

async def test_connection_params():
    """Test different connection parameters to find optimal settings."""
    
    print("🔍 Scanning for GAN cube...")
    devices = await BleakScanner.discover()
    
    device = None
    for d in devices:
        if d.name and "GAN" in d.name:
            device = d
            print(f"✅ Found: {d.name} at {d.address}")
            break
    
    if not device:
        print("❌ No GAN cube found!")
        return
    
    # Test different connection intervals
    test_configs = [
        {"name": "Default", "params": {}},
        {"name": "Low Latency", "params": {"connection_interval": (7.5, 15)}},  # min 7.5ms, max 15ms
        {"name": "Balanced", "params": {"connection_interval": (15, 30)}},
        {"name": "Power Save", "params": {"connection_interval": (30, 60)}},
    ]
    
    for config in test_configs:
        print(f"\n{'='*50}")
        print(f"Testing: {config['name']} configuration")
        print(f"{'='*50}")
        
        tester = ConnectionTester()
        
        try:
            # Try to pass connection parameters if supported
            try:
                client = BleakClient(device.address, **config['params'])
            except:
                client = BleakClient(device.address)
            
            async with client:
                print(f"Connected with {config['name']} settings")
                
                # Find notification characteristic
                for service in client.services:
                    for char in service.characteristics:
                        if "notify" in char.properties:
                            try:
                                await client.start_notify(char.uuid, tester.handle_notification)
                                print(f"📡 Receiving data for 10 seconds...")
                                
                                # Collect data for 10 seconds
                                await asyncio.sleep(10)
                                
                                await client.stop_notify(char.uuid)
                                break
                            except:
                                continue
                
                tester.print_summary()
                
        except Exception as e:
            print(f"❌ Error with {config['name']}: {e}")
        
        # Wait between tests
        if config != test_configs[-1]:
            print("\n⏳ Waiting 3 seconds before next test...")
            await asyncio.sleep(3)

async def main():
    print("BLE Connection Quality Tester")
    print("="*50)
    print("This will test different connection parameters")
    print("to find the optimal settings for smooth data flow.")
    print("Keep the cube still during testing for best results.")
    print("="*50)
    
    await test_connection_params()
    
    print("\n✅ Testing complete!")
    print("\nRecommendations:")
    print("- If delays are consistently high, try:")
    print("  1. Moving closer to the cube")
    print("  2. Disabling other Bluetooth devices")
    print("  3. Using a different Bluetooth adapter")
    print("  4. Checking for driver updates")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Test interrupted")