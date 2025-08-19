const aesjs = require('aes-js');

/**
 * Implementation for encryption scheme used in the GAN Gen2 Smart Cubes
 */
class GanGen2CubeEncrypter {
    constructor(key, iv, salt) {
        if (key.length !== 16)
            throw new Error("Key must be 16 bytes (128-bit) long");
        if (iv.length !== 16)
            throw new Error("Iv must be 16 bytes (128-bit) long");
        if (salt.length !== 6)
            throw new Error("Salt must be 6 bytes (48-bit) long");
        
        // Apply salt to key and iv
        this._key = new Uint8Array(key);
        this._iv = new Uint8Array(iv);
        for (let i = 0; i < 6; i++) {
            this._key[i] = (key[i] + salt[i]) % 0xFF;
            this._iv[i] = (iv[i] + salt[i]) % 0xFF;
        }
    }

    /** Encrypt 16-byte buffer chunk starting at offset using AES-128-CBC */
    encryptChunk(buffer, offset) {
        const cipher = new aesjs.ModeOfOperation.cbc(this._key, this._iv);
        const chunk = cipher.encrypt(buffer.subarray(offset, offset + 16));
        buffer.set(chunk, offset);
    }

    /** Decrypt 16-byte buffer chunk starting at offset using AES-128-CBC */
    decryptChunk(buffer, offset) {
        const cipher = new aesjs.ModeOfOperation.cbc(this._key, this._iv);
        const chunk = cipher.decrypt(buffer.subarray(offset, offset + 16));
        buffer.set(chunk, offset);
    }

    encrypt(data) {
        if (data.length < 16)
            throw Error('Data must be at least 16 bytes long');
        const res = new Uint8Array(data);
        // encrypt 16-byte chunk aligned to message start
        this.encryptChunk(res, 0);
        // encrypt 16-byte chunk aligned to message end
        if (res.length > 16) {
            this.encryptChunk(res, res.length - 16);
        }
        return res;
    }

    decrypt(data) {
        if (data.length < 16)
            throw Error('Data must be at least 16 bytes long');
        const res = new Uint8Array(data);
        // decrypt 16-byte chunk aligned to message end
        if (res.length > 16) {
            this.decryptChunk(res, res.length - 16);
        }
        // decrypt 16-byte chunk aligned to message start
        this.decryptChunk(res, 0);
        return res;
    }
}

/**
 * Implementation for encryption scheme used in the GAN Gen3 cubes
 */
class GanGen3CubeEncrypter extends GanGen2CubeEncrypter {
    /** 101 its just the same */
}

/**
 * Implementation for encryption scheme used in the GAN Gen4 cubes
 */
class GanGen4CubeEncrypter extends GanGen2CubeEncrypter {
    /** amazing, it's still the same */
}

module.exports = {
    GanGen2CubeEncrypter,
    GanGen3CubeEncrypter,
    GanGen4CubeEncrypter
};