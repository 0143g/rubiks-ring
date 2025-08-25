#!/usr/bin/env python3
import asyncio
import time
from collections import deque
from bleak import BleakClient, BleakScanner

CUBE_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dc4179"
CUBE_CHARACTERISTIC_UUID = "6e400003-b5a3-f393-e0a9-e50e24dc4179"

class PacketAnalyzer:
    def __init__(self):
        self.packet_times = deque(maxlen=100)
        self.packet_sizes = deque(maxlen=100)
        self.last_packet_time = None
        self.total_packets = 0
        self.duplicates = 0
        self.last_data = None
        self.delays = deque(maxlen=100)
        
    def process_packet(self, data):
        current_time = time.time()
        self.total_packets += 1
        
        # Check for duplicate data
        if self.last_data == data:
            self.duplicates += 1
            duplicate_marker = " [DUPLICATE]"
        else:
            duplicate_marker = ""
        
        self.last_data = data
        
        # Calculate inter-packet delay
        if self.last_packet_time:
            delay = (current_time - self.last_packet_time) * 1000  # ms
            self.delays.append(delay)
            delay_str = f"{delay:6.1f}ms"
            
            # Flag unusual delays
            if delay > 100:
                delay_str += " ⚠️ SLOW"
            elif delay < 10:
                delay_str += " ⚡FAST"
        else:
            delay_str = "   ---  "
        
        self.last_packet_time = current_time
        self.packet_times.append(current_time)
        self.packet_sizes.append(len(data))
        
        # Decode packet type
        packet_type = self._decode_packet_type(data)
        
        print(f"[{current_time:.3f}] {delay_str} | {len(data):2d} bytes | {data.hex()} | {packet_type}{duplicate_marker}")
        
        return delay_str
    
    def _decode_packet_type(self, data):
        if len(data) == 0:
            return "EMPTY"
        
        cmd = data[0]
        if cmd == 0x2a:
            return "ORIENTATION"
        elif cmd == 0x33:
            return "MOVE"
        elif cmd == 0x37:
            return "FACELETS"
        elif cmd == 0x32:
            return "BATTERY"
        elif cmd == 0x23:
            return "HARDWARE"
        else:
            return f"UNKNOWN(0x{cmd:02x})"
    
    def print_stats(self):
        if len(self.packet_times) > 1:
            time_span = self.packet_times[-1] - self.packet_times[0]
            rate = len(self.packet_times) / time_span if time_span > 0 else 0
            
            avg_size = sum(self.packet_sizes) / len(self.packet_sizes) if self.packet_sizes else 0
            
            if self.delays:
                avg_delay = sum(self.delays) / len(self.delays)
                max_delay = max(self.delays)
                min_delay = min(self.delays)
            else:
                avg_delay = max_delay = min_delay = 0
            
            print("\n" + "="*70)
            print(f"📊 STATS: {rate:.1f} pkt/s | Avg size: {avg_size:.1f} bytes")
            print(f"⏱️  DELAYS: Avg: {avg_delay:.1f}ms | Min: {min_delay:.1f}ms | Max: {max_delay:.1f}ms")
            print(f"📦 TOTAL: {self.total_packets} packets | {self.duplicates} duplicates")
            print("="*70 + "\n")

async def find_cube():
    print("🔍 Scanning for GAN cube...")
    devices = await BleakScanner.discover()
    for device in devices:
        if device.name and "GAN" in device.name:
            print(f"✅ Found: {device.name} at {device.address}")
            return device.address
    return None

async def analyze_ble_stream():
    address = await find_cube()
    if not address:
        print("❌ No GAN cube found!")
        return
    
    analyzer = PacketAnalyzer()
    stats_counter = 0
    
    def notification_handler(sender, data):
        nonlocal stats_counter
        analyzer.process_packet(data)
        
        stats_counter += 1
        if stats_counter >= 20:  # Print stats every 20 packets
            analyzer.print_stats()
            stats_counter = 0
    
    print(f"🔗 Connecting to {address}...")
    
    async with BleakClient(address) as client:
        print(f"✅ Connected!")
        
        # List all services and characteristics for debugging
        print("\n📋 Available services:")
        for service in client.services:
            print(f"  Service: {service.uuid}")
            for char in service.characteristics:
                print(f"    Char: {char.uuid} - Properties: {char.properties}")
        
        # Try to find the characteristic - use the exact UUID
        char_uuid = CUBE_CHARACTERISTIC_UUID
        char_found = False
        
        # Try direct approach first
        try:
            print(f"\n📡 Starting notifications on {char_uuid}...")
            await client.start_notify(char_uuid, notification_handler)
            char_found = True
        except Exception as e:
            print(f"⚠️  Direct approach failed: {e}")
            
            # Try finding in services
            for service in client.services:
                for char in service.characteristics:
                    if "notify" in char.properties:
                        try:
                            print(f"📡 Trying characteristic: {char.uuid}")
                            await client.start_notify(char.uuid, notification_handler)
                            char_found = True
                            break
                        except:
                            continue
                if char_found:
                    break
        
        if not char_found:
            print("❌ Could not start notifications!")
            return
        
        print("\n" + "="*70)
        print("STREAMING RAW BLE PACKETS - Press Ctrl+C to stop")
        print("Format: [timestamp] delay | size | hex_data | type")
        print("="*70 + "\n")
        
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Stopping...")
        
        await client.stop_notify(char.uuid)
        analyzer.print_stats()
        print("👋 Disconnected")

if __name__ == "__main__":
    try:
        asyncio.run(analyze_ble_stream())
    except KeyboardInterrupt:
        print("\n👋 Exiting...")
