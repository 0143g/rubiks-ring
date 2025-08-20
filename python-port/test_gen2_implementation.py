#!/usr/bin/env python3
"""
Test script for Gen2 implementation of GAN cube protocol.
This script tests the basic functionality without requiring an actual cube.
"""

import asyncio
import sys
import os

# Add the module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'gan_web_bluetooth'))

from gan_web_bluetooth.protocols.gen2 import GanGen2Protocol, ProtocolMessageView
from gan_web_bluetooth.protocols.base import CommandType, GanCubeCommand
from gan_web_bluetooth.encryption.encrypters import GanGen2CubeEncrypter
from gan_web_bluetooth.definitions import GAN_ENCRYPTION_KEYS, extract_mac_from_manufacturer_data
from gan_web_bluetooth.utils import Quaternion, now


def test_protocol_message_view():
    """Test the bit manipulation in ProtocolMessageView."""
    print("Testing ProtocolMessageView bit manipulation...")
    
    # Test data with known bit patterns
    test_data = bytes([0xFF, 0x00, 0xAA, 0x55])  # 11111111 00000000 10101010 01010101
    msg = ProtocolMessageView(test_data)
    
    # Test getting first 4 bits (should be 15 = 0xF)
    assert msg.get_bit_word(0, 4) == 15, f"Expected 15, got {msg.get_bit_word(0, 4)}"
    
    # Test getting bits across byte boundary  
    # Bits 6-9: last 2 bits of first byte (11) + first 2 bits of second byte (00) = 1100 = 12
    assert msg.get_bit_word(6, 4) == 12, f"Expected 12, got {msg.get_bit_word(6, 4)}"
    
    print("✓ ProtocolMessageView tests passed")


def test_encryption():
    """Test encryption/decryption."""
    print("Testing Gen2 encryption...")
    
    # Use standard GAN key
    key_data = GAN_ENCRYPTION_KEYS[0]
    key = bytes(key_data['key'])
    iv = bytes(key_data['iv'])
    
    # Create fake MAC salt
    salt = bytes([0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC])
    
    encrypter = GanGen2CubeEncrypter(key, iv, salt)
    
    # Test with 20-byte message (typical command size)
    original = b'\x04' + b'\x00' * 19  # REQUEST_FACELETS command
    
    encrypted = encrypter.encrypt(original)
    decrypted = encrypter.decrypt(encrypted)
    
    assert len(encrypted) == len(original), f"Length mismatch: {len(encrypted)} vs {len(original)}"
    assert decrypted == original, "Decryption failed"
    
    print("✓ Encryption tests passed")


def test_protocol_commands():
    """Test protocol command encoding."""
    print("Testing Gen2 protocol command encoding...")
    
    # Create protocol instance with encryption
    key_data = GAN_ENCRYPTION_KEYS[0]
    encrypter = GanGen2CubeEncrypter(
        bytes(key_data['key']),
        bytes(key_data['iv']),
        bytes([0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC])  # fake salt
    )
    
    protocol = GanGen2Protocol(encrypter)
    
    # Test different command types
    commands = [
        (CommandType.REQUEST_FACELETS, 0x04),
        (CommandType.REQUEST_HARDWARE, 0x05),
        (CommandType.REQUEST_BATTERY, 0x09),
    ]
    
    for cmd_type, expected_first_byte in commands:
        cmd = GanCubeCommand(type=cmd_type)
        encoded = protocol.encode_command(cmd)
        
        assert encoded is not None, f"Failed to encode {cmd_type}"
        assert len(encoded) == 20, f"Wrong length for {cmd_type}: {len(encoded)}"
        
        # Decrypt to check first byte
        decrypted = encrypter.decrypt(encoded)
        assert decrypted[0] == expected_first_byte, f"Wrong first byte for {cmd_type}: {decrypted[0]} vs {expected_first_byte}"
    
    print("✓ Protocol command tests passed")


def test_mac_extraction():
    """Test MAC address extraction from manufacturer data."""
    print("Testing MAC address extraction...")
    
    # Simulate manufacturer data with MAC in last 6 bytes
    fake_manufacturer_data = {
        0x0101: bytes([0x01, 0x02, 0x03, 0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC])
    }
    
    mac = extract_mac_from_manufacturer_data(fake_manufacturer_data)
    expected_mac = "BC:9A:78:56:34:12"  # reversed order
    
    assert mac == expected_mac, f"MAC extraction failed: {mac} vs {expected_mac}"
    
    print("✓ MAC extraction tests passed")


def test_quaternion_utils():
    """Test quaternion utility functions."""
    print("Testing quaternion utilities...")
    
    from gan_web_bluetooth.utils import normalize_quaternion, slerp_quaternions
    
    # Test normalization
    q = Quaternion(x=1, y=1, z=1, w=1)
    normalized = normalize_quaternion(q)
    
    # Should be unit length
    length = (normalized.x**2 + normalized.y**2 + normalized.z**2 + normalized.w**2)**0.5
    assert abs(length - 1.0) < 1e-6, f"Quaternion not normalized: length = {length}"
    
    # Test SLERP
    q1 = Quaternion(x=0, y=0, z=0, w=1)  # identity
    q2 = Quaternion(x=0, y=0, z=1, w=0)  # 180 degree rotation around Z
    
    interpolated = slerp_quaternions(q1, q2, 0.5)  # halfway
    assert interpolated is not None, "SLERP failed"
    
    print("✓ Quaternion utility tests passed")


def main():
    """Run all tests."""
    print("Testing GAN Gen2 Python implementation...")
    print("=" * 50)
    
    try:
        test_protocol_message_view()
        test_encryption()
        test_protocol_commands()
        test_mac_extraction()
        test_quaternion_utils()
        
        print("=" * 50)
        print("✅ All tests passed! Gen2 implementation is working correctly.")
        print("\nYou can now try connecting to your Gen2 GAN cube using:")
        print("  python examples/cube_example.py")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())