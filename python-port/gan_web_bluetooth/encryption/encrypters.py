"""AES encryption implementations for different GAN cube generations."""

from typing import Protocol
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend


class GanCubeEncrypter(Protocol):
    """Common cube encrypter interface."""
    
    def encrypt(self, data: bytes) -> bytes:
        """Encrypt binary message buffer."""
        ...
    
    def decrypt(self, data: bytes) -> bytes:
        """Decrypt binary message buffer."""
        ...


class GanGen2CubeEncrypter:
    """Implementation for encryption scheme used in the GAN Gen2 Smart Cubes."""
    
    def __init__(self, key: bytes, iv: bytes, salt: bytes):
        """
        Initialize Gen2 encrypter with key, IV, and salt.
        
        Args:
            key: 16-byte AES key
            iv: 16-byte initialization vector
            salt: 6-byte salt (typically from MAC address)
        
        Raises:
            ValueError: If key, IV, or salt have incorrect length
        """
        if len(key) != 16:
            raise ValueError("Key must be 16 bytes (128-bit) long")
        if len(iv) != 16:
            raise ValueError("IV must be 16 bytes (128-bit) long")
        if len(salt) != 6:
            raise ValueError("Salt must be 6 bytes (48-bit) long")
        
        # Apply salt to key and IV
        self._key = bytearray(key)
        self._iv = bytearray(iv)
        for i in range(6):
            self._key[i] = (key[i] + salt[i]) % 0xFF
            self._iv[i] = (iv[i] + salt[i]) % 0xFF
        
        self._key = bytes(self._key)
        self._iv = bytes(self._iv)
        self._backend = default_backend()
    
    def _encrypt_chunk(self, data: bytearray, offset: int) -> None:
        """
        Encrypt 16-byte chunk at offset using AES-128-CBC.
        
        Args:
            data: Buffer to encrypt in-place
            offset: Starting offset for 16-byte chunk
        """
        cipher = Cipher(
            algorithms.AES(self._key),
            modes.CBC(self._iv),
            backend=self._backend
        )
        encryptor = cipher.encryptor()
        chunk = data[offset:offset + 16]
        encrypted = encryptor.update(chunk) + encryptor.finalize()
        data[offset:offset + 16] = encrypted
    
    def _decrypt_chunk(self, data: bytearray, offset: int) -> None:
        """
        Decrypt 16-byte chunk at offset using AES-128-CBC.
        
        Args:
            data: Buffer to decrypt in-place
            offset: Starting offset for 16-byte chunk
        """
        cipher = Cipher(
            algorithms.AES(self._key),
            modes.CBC(self._iv),
            backend=self._backend
        )
        decryptor = cipher.decryptor()
        chunk = data[offset:offset + 16]
        decrypted = decryptor.update(chunk) + decryptor.finalize()
        data[offset:offset + 16] = decrypted
    
    def encrypt(self, data: bytes) -> bytes:
        """
        Encrypt data using GAN Gen2 scheme.
        
        Encrypts 16-byte chunk at start and (if data > 16 bytes) 
        16-byte chunk at end.
        
        Args:
            data: Data to encrypt (must be at least 16 bytes)
        
        Returns:
            Encrypted data
        
        Raises:
            ValueError: If data is less than 16 bytes
        """
        if len(data) < 16:
            raise ValueError("Data must be at least 16 bytes long")
        
        result = bytearray(data)
        
        # Encrypt 16-byte chunk aligned to message start
        self._encrypt_chunk(result, 0)
        
        # Encrypt 16-byte chunk aligned to message end
        if len(result) > 16:
            self._encrypt_chunk(result, len(result) - 16)
        
        return bytes(result)
    
    def decrypt(self, data: bytes) -> bytes:
        """
        Decrypt data using GAN Gen2 scheme.
        
        Decrypts in reverse order: end chunk first, then start chunk.
        
        Args:
            data: Data to decrypt (must be at least 16 bytes)
        
        Returns:
            Decrypted data
        
        Raises:
            ValueError: If data is less than 16 bytes
        """
        if len(data) < 16:
            raise ValueError("Data must be at least 16 bytes long")
        
        result = bytearray(data)
        
        # Decrypt 16-byte chunk aligned to message end
        if len(result) > 16:
            self._decrypt_chunk(result, len(result) - 16)
        
        # Decrypt 16-byte chunk aligned to message start
        self._decrypt_chunk(result, 0)
        
        return bytes(result)


class GanGen3CubeEncrypter(GanGen2CubeEncrypter):
    """Implementation for encryption scheme used in the GAN Gen3 cubes."""
    # Gen3 uses the same encryption as Gen2
    pass


class GanGen4CubeEncrypter(GanGen2CubeEncrypter):
    """Implementation for encryption scheme used in the GAN Gen4 cubes."""
    # Gen4 also uses the same encryption as Gen2
    pass