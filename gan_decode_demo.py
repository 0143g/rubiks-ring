#!/usr/bin/env python3
"""
GAN Cube Bluetooth Packet Decoder Demo
Educational demonstration of the complete decoding pipeline from raw encrypted hex to meaningful data.
"""

import struct
from typing import List, Tuple, Optional
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from dataclasses import dataclass


@dataclass
class Quaternion:
    """Normalized quaternion for orientation."""
    x: float
    y: float
    z: float
    w: float


class GanPacketDecoder:
    """Decoder for GAN Gen2 Bluetooth packets."""

    def __init__(self, mac_address: str = "D3:CA:1A:0D:18:87"):
        """
        Initialize decoder with encryption keys.

        Args:
            mac_address: MAC address of the cube (for key derivation)
        """
        # Default GAN Gen2 encryption keys
        self.base_key = bytes([
            0x01, 0x02, 0x42, 0x28, 0x31, 0x91, 0x16, 0x07,
            0x20, 0x05, 0x18, 0x54, 0x42, 0x11, 0x12, 0x53
        ])
        self.base_iv = bytes([
            0x11, 0x03, 0x32, 0x28, 0x21, 0x01, 0x76, 0x27,
            0x20, 0x95, 0x78, 0x14, 0x32, 0x12, 0x02, 0x43
        ])

        # Convert MAC to salt (reversed bytes)
        mac_parts = mac_address.split(":")
        self.salt = bytes([int(p, 16) for p in reversed(mac_parts)])

        # Apply salt to key and IV (first 6 bytes)
        self.key = bytearray(self.base_key)
        self.iv = bytearray(self.base_iv)
        for i in range(6):
            self.key[i] = (self.base_key[i] + self.salt[i]) % 0xFF
            self.iv[i] = (self.base_iv[i] + self.salt[i]) % 0xFF

        self.key = bytes(self.key)
        self.iv = bytes(self.iv)

    def decrypt_packet(self, hex_data: str) -> bytes:
        """
        Decrypt a 20-byte packet using GAN Gen2 scheme.

        The scheme decrypts:
        1. Last 16 bytes if packet > 16 bytes (bytes 4-19)
        2. First 16 bytes (bytes 0-15)
        """
        # Convert hex string to bytes
        encrypted = bytes.fromhex(hex_data)
        result = bytearray(encrypted)

        # Decrypt last 16-byte chunk (aligned to end)
        if len(result) == 20:
            cipher = Cipher(
                algorithms.AES(self.key),
                modes.CBC(self.iv),
                backend=default_backend()
            )
            decryptor = cipher.decryptor()
            chunk = result[4:20]
            decrypted_chunk = decryptor.update(chunk) + decryptor.finalize()
            result[4:20] = decrypted_chunk

        # Decrypt first 16-byte chunk
        cipher = Cipher(
            algorithms.AES(self.key),
            modes.CBC(self.iv),
            backend=default_backend()
        )
        decryptor = cipher.decryptor()
        chunk = result[0:16]
        decrypted_chunk = decryptor.update(chunk) + decryptor.finalize()
        result[0:16] = decrypted_chunk

        return bytes(result)

    def parse_event_type(self, data: bytes) -> Tuple[int, str]:
        """Extract event type from first 4 bits."""
        event_type = (data[0] >> 4) & 0x0F

        event_names = {
            0x01: "GYRO/ORIENTATION",
            0x02: "MOVE",
            0x03: "FACELETS",
            0x04: "FACELETS",
            0x05: "HARDWARE",
            0x09: "BATTERY",
            0x0D: "DISCONNECT"
        }

        return event_type, event_names.get(event_type, f"UNKNOWN_{event_type:02X}")

    def bits_to_string(self, data: bytes) -> str:
        """Convert bytes to bit string for bit-level parsing."""
        return ''.join(f'{byte:08b}' for byte in data)

    def get_bit_word(self, bits: str, offset: int, length: int) -> int:
        """Extract bits from bit string."""
        bit_slice = bits[offset:offset + length]
        return int(bit_slice, 2) if bit_slice else 0

    def parse_orientation(self, data: bytes) -> dict:
        """Parse orientation/gyro event."""
        bits = self.bits_to_string(data)

        # Extract quaternion components (16 bits each)
        qw_raw = self.get_bit_word(bits, 4, 16)
        qx_raw = self.get_bit_word(bits, 20, 16)
        qy_raw = self.get_bit_word(bits, 36, 16)
        qz_raw = self.get_bit_word(bits, 52, 16)

        # Convert to normalized quaternion
        # Format: sign bit (bit 15) + 15-bit magnitude normalized to [-1, 1]
        qx = (1 - (qx_raw >> 15) * 2) * (qx_raw & 0x7FFF) / 0x7FFF
        qy = (1 - (qy_raw >> 15) * 2) * (qy_raw & 0x7FFF) / 0x7FFF
        qz = (1 - (qz_raw >> 15) * 2) * (qz_raw & 0x7FFF) / 0x7FFF
        qw = (1 - (qw_raw >> 15) * 2) * (qw_raw & 0x7FFF) / 0x7FFF

        return {
            "type": "ORIENTATION",
            "raw_values": {
                "qw": f"0x{qw_raw:04X}",
                "qx": f"0x{qx_raw:04X}",
                "qy": f"0x{qy_raw:04X}",
                "qz": f"0x{qz_raw:04X}"
            },
            "quaternion": Quaternion(x=qx, y=qy, z=qz, w=qw),
            "euler_approx": self.quaternion_to_euler(qx, qy, qz, qw)
        }

    def quaternion_to_euler(self, x: float, y: float, z: float, w: float) -> dict:
        """Approximate Euler angles from quaternion."""
        import math

        # Roll (x-axis rotation)
        sinr_cosp = 2 * (w * x + y * z)
        cosr_cosp = 1 - 2 * (x * x + y * y)
        roll = math.atan2(sinr_cosp, cosr_cosp)

        # Pitch (y-axis rotation)
        sinp = 2 * (w * y - z * x)
        pitch = math.asin(max(-1, min(1, sinp)))

        # Yaw (z-axis rotation)
        siny_cosp = 2 * (w * z + x * y)
        cosy_cosp = 1 - 2 * (y * y + z * z)
        yaw = math.atan2(siny_cosp, cosy_cosp)

        return {
            "roll_deg": math.degrees(roll),
            "pitch_deg": math.degrees(pitch),
            "yaw_deg": math.degrees(yaw)
        }

    def parse_move(self, data: bytes) -> dict:
        """Parse move event."""
        bits = self.bits_to_string(data)

        # Extract serial number and moves
        serial = self.get_bit_word(bits, 4, 8)

        moves = []
        # Up to 7 moves can be packed in one event
        for i in range(7):
            face = self.get_bit_word(bits, 12 + 5 * i, 4)
            direction = self.get_bit_word(bits, 16 + 5 * i, 1)

            # Check if this move slot is used (face < 6)
            if face < 6:
                face_chars = "URFDLB"
                move_str = face_chars[face] + ("'" if direction == 1 else "")

                # Extract timestamp for this move
                elapsed = self.get_bit_word(bits, 47 + 16 * i, 16)

                moves.append({
                    "face": face,
                    "direction": "CCW" if direction == 1 else "CW",
                    "notation": move_str,
                    "elapsed_ms": elapsed
                })

        return {
            "type": "MOVE",
            "serial": serial,
            "moves": moves
        }

    def parse_battery(self, data: bytes) -> dict:
        """Parse battery event."""
        bits = self.bits_to_string(data)
        battery_percent = self.get_bit_word(bits, 8, 8)

        return {
            "type": "BATTERY",
            "percent": min(battery_percent, 100)
        }

    def decode_packet(self, hex_data: str) -> dict:
        """
        Complete decoding pipeline for a packet.
        """
        print(f"\n{'='*80}")
        print(f"RAW HEX PACKET: {hex_data}")
        print(f"{'='*80}")

        # Step 1: Decrypt
        print("\n1. AES DECRYPTION")
        print(f"   MAC Address: D3:CA:1A:0D:18:87")
        print(f"   Salt (reversed MAC): {self.salt.hex()}")
        print(f"   Key (first 6 bytes salted): {self.key.hex()}")
        print(f"   IV (first 6 bytes salted): {self.iv.hex()}")

        decrypted = self.decrypt_packet(hex_data)
        print(f"\n   DECRYPTED BYTES: {decrypted.hex()}")
        print(f"   Binary: {' '.join(f'{b:08b}' for b in decrypted[:4])}")

        # Step 2: Parse event type
        event_type, event_name = self.parse_event_type(decrypted)
        print(f"\n2. EVENT TYPE IDENTIFICATION")
        print(f"   First byte: 0x{decrypted[0]:02X} = {decrypted[0]:08b}")
        print(f"   Event type (bits 0-3): {event_type:04b} = 0x{event_type:X}")
        print(f"   Event name: {event_name}")

        # Step 3: Parse based on event type
        print(f"\n3. EVENT-SPECIFIC PARSING")

        if event_type == 0x01:
            result = self.parse_orientation(decrypted)
            print(f"   Quaternion raw values:")
            for k, v in result['raw_values'].items():
                print(f"     {k}: {v}")
            print(f"\n   Normalized quaternion:")
            q = result['quaternion']
            print(f"     x={q.x:.4f}, y={q.y:.4f}, z={q.z:.4f}, w={q.w:.4f}")
            print(f"\n   Euler angles (approximate):")
            for k, v in result['euler_approx'].items():
                print(f"     {k}: {v:.2f}°")

        elif event_type == 0x02:
            result = self.parse_move(decrypted)
            print(f"   Serial number: {result['serial']}")
            if result['moves']:
                print(f"   Moves decoded:")
                for i, move in enumerate(result['moves']):
                    print(f"     Move {i+1}: {move['notation']} (face={move['face']}, dir={move['direction']}, elapsed={move['elapsed_ms']}ms)")
            else:
                print(f"   No moves in this packet")

        elif event_type == 0x09:
            result = self.parse_battery(decrypted)
            print(f"   Battery level: {result['percent']}%")

        else:
            result = {"type": event_name, "raw": decrypted.hex()}
            print(f"   Raw data: {decrypted.hex()}")

        print(f"\n4. FINAL DECODED RESULT")
        print(f"   {result}")

        return result


def main():
    """Demonstrate decoding of sample packets from OUTPUT.txt"""

    # Initialize decoder
    decoder = GanPacketDecoder(mac_address="D3:CA:1A:0D:18:87")

    # Select representative packets
    sample_packets = [
        # These are from OUTPUT.txt - actual encrypted packets from a GAN cube
        "9dd006d0b39605bc891cea688b94abdbc124dec1",  # Packet 1
        "cbea4ed308df6c77c31afee4d02ad6b297c406be",  # Packet 2
        "451ed604dc7535c778ba89a6f617e18dbac4244b",  # Packet 3
        "b066cb4009a3e86232e655b76bf61ab6f49130e0",  # Packet 4
        "5b729a665086910ee3b1f6ee89dcb22ec1b3aff3",  # Packet 5
    ]

    print("\n" + "="*80)
    print("GAN CUBE BLUETOOTH PACKET DECODER - EDUCATIONAL DEMO")
    print("="*80)
    print("\nThis demonstrates the complete decoding pipeline:")
    print("1. AES-CBC decryption with MAC-based salt")
    print("2. Event type identification from bit patterns")
    print("3. Bit-level field extraction")
    print("4. Value normalization (quaternions, moves, etc.)")

    # Decode each packet
    results = []
    for i, packet in enumerate(sample_packets[:3], 1):  # Demo first 3
        print(f"\n\n{'*'*80}")
        print(f"PACKET {i}")
        print(f"{'*'*80}")

        try:
            result = decoder.decode_packet(packet)
            results.append(result)
        except Exception as e:
            print(f"Error decoding packet: {e}")
            results.append({"error": str(e)})

    # Summary
    print("\n\n" + "="*80)
    print("DECODING SUMMARY")
    print("="*80)

    print("\n🔐 ENCRYPTION:")
    print("  • Uses AES-128-CBC with MAC address as salt")
    print("  • Salt = reversed MAC bytes")
    print("  • Key/IV first 6 bytes modified by (base + salt) % 0xFF")
    print("  • Decrypts in two chunks: bytes[4:20] then bytes[0:16]")

    print("\n📊 EVENT IDENTIFICATION:")
    print("  • Event type in bits 0-3 of first byte")
    print("  • 0x01 = Orientation (quaternion)")
    print("  • 0x02 = Move (face turns)")
    print("  • 0x09 = Battery level")

    print("\n🔢 BIT-LEVEL PARSING:")
    print("  • Data packed at arbitrary bit boundaries")
    print("  • Quaternions: 16 bits each (1 sign + 15 magnitude)")
    print("  • Moves: 5 bits per move (4 face + 1 direction)")
    print("  • Timestamps: 16 bits for elapsed time")

    print("\n📐 NORMALIZATION:")
    print("  • Quaternions: raw/0x7FFF with sign from bit 15")
    print("  • Moves: face index to URFDLB notation")
    print("  • Direction: 0=CW, 1=CCW (prime notation)")

    print("\n✅ DECODED EVENT TYPES:")
    event_counts = {}
    for r in results:
        if 'type' in r:
            event_type = r['type']
            event_counts[event_type] = event_counts.get(event_type, 0) + 1

    for event_type, count in event_counts.items():
        print(f"  • {event_type}: {count} packet(s)")


if __name__ == "__main__":
    main()