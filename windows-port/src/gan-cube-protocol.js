const { now, toKociembaFacelets, smoothOrientationData, cubeTimestampLinearFit } = require('./utils');
const { EventEmitter } = require('events');

/** Calculate sum of all numbers in array */
const sum = arr => arr.reduce((a, v) => a + v, 0);

/**
 * View for binary protocol messages allowing to retrieve from message arbitrary length bit words
 */
class GanProtocolMessageView {
    constructor(message) {
        this.bits = Array.from(message).map(byte => (byte + 0x100).toString(2).slice(1)).join('');
    }

    getBitWord(startBit, bitLength, littleEndian = false) {
        if (bitLength <= 8) {
            return parseInt(this.bits.slice(startBit, startBit + bitLength), 2);
        } else if (bitLength == 16 || bitLength == 32) {
            let buf = new Uint8Array(bitLength / 8);
            for (let i = 0; i < buf.length; i++) {
                buf[i] = parseInt(this.bits.slice(8 * i + startBit, 8 * i + startBit + 8), 2);
            }
            let dv = new DataView(buf.buffer);
            return bitLength == 16 ? dv.getUint16(0, littleEndian) : dv.getUint32(0, littleEndian);
        } else {
            throw new Error('Unsupproted bit word length');
        }
    }
}

/**
 * Driver implementation for GAN Gen2 protocol, supported cubes:
 *  - GAN Mini ui FreePlay
 *  - GAN12 ui FreePlay
 *  - GAN12 ui
 *  - GAN356 i Carry S
 *  - GAN356 i Carry
 *  - GAN356 i 3
 *  - Monster Go 3Ai
 */
class GanGen2ProtocolDriver {
    constructor() {
        this.lastSerial = -1;
        this.lastMoveTimestamp = 0;
        this.cubeTimestamp = 0;
        
        // Gyroscope smoothing system
        this.gyroBuffer = [];
        this.GYRO_BUFFER_SIZE = 5;
        this.GYRO_RATE_LIMIT_MS = 16; // 60 FPS max
        this.lastGyroEmit = 0;
        
        // Timestamp synchronization for gyro events
        this.gyroTimestampHistory = [];
        this.MAX_TIMESTAMP_HISTORY = 20;
    }

    /**
     * Process and smooth gyroscope data for optimal performance
     */
    processGyroData(quaternion, timestamp, cubeTimestamp) {
        // Rate limiting - prevent overwhelming the stream
        if (timestamp - this.lastGyroEmit < this.GYRO_RATE_LIMIT_MS) {
            return null;
        }

        // Update timestamp synchronization if cube timestamp available
        if (cubeTimestamp !== undefined) {
            this.updateTimestampSync(cubeTimestamp, timestamp);
        }

        // Add to buffer
        this.gyroBuffer.push({ quaternion, timestamp });
        
        // Maintain buffer size
        if (this.gyroBuffer.length > this.GYRO_BUFFER_SIZE) {
            this.gyroBuffer.shift();
        }

        // Apply smoothing if we have enough samples
        const smoothedQuaternion = smoothOrientationData(this.gyroBuffer, Math.min(3, this.gyroBuffer.length));
        
        if (smoothedQuaternion) {
            this.lastGyroEmit = timestamp;
            return {
                type: "GYRO",
                timestamp: timestamp,
                quaternion: smoothedQuaternion,
                velocity: this.calculateAngularVelocity()
            };
        }

        return null;
    }

    /**
     * Update timestamp synchronization data for gyro events
     */
    updateTimestampSync(cubeTime, hostTime) {
        this.gyroTimestampHistory.push({ cubeTime, hostTime });
        
        // Maintain history size
        if (this.gyroTimestampHistory.length > this.MAX_TIMESTAMP_HISTORY) {
            this.gyroTimestampHistory.shift();
        }
    }

    /**
     * Get synchronized timestamp using linear regression on gyro data
     */
    getSynchronizedTimestamp(cubeTimestamp) {
        if (this.gyroTimestampHistory.length < 2) {
            return now();
        }

        const fit = cubeTimestampLinearFit(this.gyroTimestampHistory);
        return Math.round(fit.slope * cubeTimestamp + fit.intercept);
    }

    /**
     * Calculate angular velocity from recent orientation changes
     */
    calculateAngularVelocity() {
        if (this.gyroBuffer.length < 2) return undefined;

        const recent = this.gyroBuffer.slice(-2);
        const dt = (recent[1].timestamp - recent[0].timestamp) / 1000; // Convert to seconds
        
        if (dt <= 0) return undefined;

        // Simplified angular velocity calculation
        // In production, this could use more sophisticated quaternion differentiation
        const q1 = recent[0].quaternion;
        const q2 = recent[1].quaternion;
        
        return {
            x: (q2.x - q1.x) / dt,
            y: (q2.y - q1.y) / dt,
            z: (q2.z - q1.z) / dt
        };
    }

    createCommandMessage(command) {
        let msg = new Uint8Array(20).fill(0);
        switch (command.type) {
            case 'REQUEST_FACELETS':
                msg[0] = 0x04;
                break;
            case 'REQUEST_HARDWARE':
                msg[0] = 0x05;
                break;
            case 'REQUEST_BATTERY':
                msg[0] = 0x09;
                break;
            case 'REQUEST_RESET':
                msg.set([0x0A, 0x05, 0x39, 0x77, 0x00, 0x00, 0x01, 0x23, 0x45, 0x67, 0x89, 0xAB, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]);
                break;
            default:
                msg = undefined;
        }
        return msg;
    }

    async handleStateEvent(conn, eventMessage) {
        const timestamp = now();
        const cubeEvents = [];
        const msg = new GanProtocolMessageView(eventMessage);
        const eventType = msg.getBitWord(0, 4);

        // Debug: Log raw message analysis
        const rawBytes = Array.from(eventMessage).map(b => b.toString(16).padStart(2, '0')).join(' ');
        const rawBinary = Array.from(eventMessage).map(b => (b + 0x100).toString(2).slice(1)).join(' ');
        const eventTypeByte = msg.getBitWord(0, 8); // Try full byte
        console.log(`[GAN Gen2] Raw message: ${rawBytes}`);
        console.log(`[GAN Gen2] Binary (first 32 bits): ${rawBinary.slice(0, 35)}`);
        console.log(`[GAN Gen2] Event type (first 4 bits): 0x${eventType.toString(16)} (${eventType})`);
        console.log(`[GAN Gen2] Event type (first 8 bits): 0x${eventTypeByte.toString(16)} (${eventTypeByte})`);

        if (eventType == 0x01) { // GYRO
            // Orientation Quaternion - parse raw data
            let qw = msg.getBitWord(4, 16);
            let qx = msg.getBitWord(20, 16);
            let qy = msg.getBitWord(36, 16);
            let qz = msg.getBitWord(52, 16);

            // Convert to normalized quaternion
            const rawQuaternion = {
                x: (1 - (qx >> 15) * 2) * (qx & 0x7FFF) / 0x7FFF,
                y: (1 - (qy >> 15) * 2) * (qy & 0x7FFF) / 0x7FFF,
                z: (1 - (qz >> 15) * 2) * (qz & 0x7FFF) / 0x7FFF,
                w: (1 - (qw >> 15) * 2) * (qw & 0x7FFF) / 0x7FFF
            };

            // Process through smoothing system
            const smoothedGyroEvent = this.processGyroData(rawQuaternion, timestamp);
            if (smoothedGyroEvent) {
                cubeEvents.push(smoothedGyroEvent);
            }

        } else if (eventType == 0x02) { // MOVE
            if (this.lastSerial != -1) { // Accept move events only after first facelets state event received
                let serial = msg.getBitWord(4, 8);
                let diff = Math.min((serial - this.lastSerial) & 0xFF, 7);
                this.lastSerial = serial;

                if (diff > 0) {
                    for (let i = diff - 1; i >= 0; i--) {
                        let face = msg.getBitWord(12 + 5 * i, 4);
                        let direction = msg.getBitWord(16 + 5 * i, 1);
                        let move = "URFDLB".charAt(face) + " '".charAt(direction);
                        let elapsed = msg.getBitWord(47 + 16 * i, 16);
                        if (elapsed == 0) { // In case of 16-bit cube timestamp register overflow
                            elapsed = timestamp - this.lastMoveTimestamp;
                        }
                        this.cubeTimestamp += elapsed;
                        cubeEvents.push({
                            type: "MOVE",
                            serial: (serial - i) & 0xFF,
                            timestamp: timestamp,
                            localTimestamp: i == 0 ? timestamp : null, // Missed and recovered events has no meaningfull local timestamps
                            cubeTimestamp: this.cubeTimestamp,
                            face: face,
                            direction: direction,
                            move: move.trim()
                        });
                    }
                    this.lastMoveTimestamp = timestamp;
                }
            }

        } else if (eventType == 0x04) { // FACELETS
            let serial = msg.getBitWord(4, 8);

            if (this.lastSerial == -1)
                this.lastSerial = serial;

            // Corner/Edge Permutation/Orientation
            let cp = [];
            let co = [];
            let ep = [];
            let eo = [];

            // Corners
            for (let i = 0; i < 7; i++) {
                cp.push(msg.getBitWord(12 + i * 3, 3));
                co.push(msg.getBitWord(33 + i * 2, 2));
            }
            cp.push(28 - sum(cp));
            co.push((3 - (sum(co) % 3)) % 3);

            // Edges
            for (let i = 0; i < 11; i++) {
                ep.push(msg.getBitWord(47 + i * 4, 4));
                eo.push(msg.getBitWord(91 + i, 1));
            }
            ep.push(66 - sum(ep));
            eo.push((2 - (sum(eo) % 2)) % 2);

            // Debug logging for problematic data
            console.log('[GAN Gen2] FACELETS parsed:', { 
                serial, 
                cpLen: cp.length, coLen: co.length, epLen: ep.length, eoLen: eo.length,
                cp: cp.slice(0, 3), // Log first few values to avoid spam
                ep: ep.slice(0, 3),
                cpSum: sum(cp.slice(0, 7)), epSum: sum(ep.slice(0, 11))
            });

            cubeEvents.push({
                type: "FACELETS",
                serial: serial,
                timestamp: timestamp,
                facelets: toKociembaFacelets(cp, co, ep, eo),
                state: {
                    CP: cp,
                    CO: co,
                    EP: ep,
                    EO: eo
                },
            });

        } else if (eventType == 0x05) { // HARDWARE
            let hwMajor = msg.getBitWord(8, 8);
            let hwMinor = msg.getBitWord(16, 8);
            let swMajor = msg.getBitWord(24, 8);
            let swMinor = msg.getBitWord(32, 8);
            let gyroSupported = msg.getBitWord(104, 1);

            let hardwareName = '';
            for (var i = 0; i < 8; i++) {
                hardwareName += String.fromCharCode(msg.getBitWord(i * 8 + 40, 8));
            }

            cubeEvents.push({
                type: "HARDWARE",
                timestamp: timestamp,
                hardwareName: hardwareName,
                hardwareVersion: `${hwMajor}.${hwMinor}`,
                softwareVersion: `${swMajor}.${swMinor}`,
                gyroSupported: !!gyroSupported
            });

        } else if (eventType == 0x09) { // BATTERY
            let batteryLevel = msg.getBitWord(8, 8);

            cubeEvents.push({
                type: "BATTERY",
                timestamp: timestamp,
                batteryLevel: Math.min(batteryLevel, 100)
            });

        } else if (eventType == 0x0D) { // DISCONNECT
            conn.disconnect();
        } else {
            // Unknown event type
            console.warn(`[GAN Gen2] Unknown event type: 0x${eventType.toString(16)} (${eventType})`);
            console.warn(`[GAN Gen2] Full message bytes: ${Array.from(eventMessage).map(b => b.toString(16).padStart(2, '0')).join(' ')}`);
        }

        return cubeEvents;
    }
}

/**
 * Driver implementation for GAN Gen3 protocol, supported cubes:
 *  - GAN356 i Carry 2
 */
class GanGen3ProtocolDriver {
    constructor() {
        this.serial = -1;
        this.lastSerial = -1;
        this.lastLocalTimestamp = null;
        this.moveBuffer = [];
    }

    createCommandMessage(command) {
        let msg = new Uint8Array(16).fill(0);
        switch (command.type) {
            case 'REQUEST_FACELETS':
                msg.set([0x68, 0x01]);
                break;
            case 'REQUEST_HARDWARE':
                msg.set([0x68, 0x04]);
                break;
            case 'REQUEST_BATTERY':
                msg.set([0x68, 0x07]);
                break;
            case 'REQUEST_RESET':
                msg.set([0x68, 0x05, 0x05, 0x39, 0x77, 0x00, 0x00, 0x01, 0x23, 0x45, 0x67, 0x89, 0xAB, 0x00, 0x00, 0x00]);
                break;
            default:
                msg = undefined;
        }
        return msg;
    }

    async handleStateEvent(conn, eventMessage) {
        const timestamp = now();
        const cubeEvents = [];
        const msg = new GanProtocolMessageView(eventMessage);

        const magic = msg.getBitWord(0, 8);
        const eventType = msg.getBitWord(8, 8);
        const dataLength = msg.getBitWord(16, 8);

        if (magic == 0x55 && dataLength > 0) {
            if (eventType == 0x01) { // MOVE
                if (this.lastSerial != -1) {
                    this.lastLocalTimestamp = timestamp;
                    let cubeTimestamp = msg.getBitWord(24, 32, true);
                    let serial = this.serial = msg.getBitWord(56, 16, true);

                    let direction = msg.getBitWord(72, 2);
                    let face = [2, 32, 8, 1, 16, 4].indexOf(msg.getBitWord(74, 6));
                    let move = "URFDLB".charAt(face) + " '".charAt(direction);

                    if (face >= 0) {
                        cubeEvents.push({
                            type: "MOVE",
                            serial: serial,
                            timestamp: timestamp,
                            localTimestamp: timestamp,
                            cubeTimestamp: cubeTimestamp,
                            face: face,
                            direction: direction,
                            move: move.trim()
                        });
                    }
                }
            } else if (eventType == 0x02) { // FACELETS
                let serial = this.serial = msg.getBitWord(24, 16, true);

                if (this.lastSerial == -1)
                    this.lastSerial = serial;

                // Corner/Edge Permutation/Orientation  
                let cp = [];
                let co = [];
                let ep = [];
                let eo = [];

                // Corners
                for (let i = 0; i < 7; i++) {
                    cp.push(msg.getBitWord(40 + i * 3, 3));
                    co.push(msg.getBitWord(61 + i * 2, 2));
                }
                cp.push(28 - sum(cp));
                co.push((3 - (sum(co) % 3)) % 3);

                // Edges
                for (let i = 0; i < 11; i++) {
                    ep.push(msg.getBitWord(77 + i * 4, 4));
                    eo.push(msg.getBitWord(121 + i, 1));
                }
                ep.push(66 - sum(ep));
                eo.push((2 - (sum(eo) % 2)) % 2);

                cubeEvents.push({
                    type: "FACELETS",
                    serial: serial,
                    timestamp: timestamp,
                    facelets: toKociembaFacelets(cp, co, ep, eo),
                    state: {
                        CP: cp,
                        CO: co,
                        EP: ep,
                        EO: eo
                    },
                });
            } else if (eventType == 0x07) { // HARDWARE
                let swMajor = msg.getBitWord(72, 4);
                let swMinor = msg.getBitWord(76, 4);
                let hwMajor = msg.getBitWord(80, 4);
                let hwMinor = msg.getBitWord(84, 4);

                let hardwareName = '';
                for (var i = 0; i < 5; i++) {
                    hardwareName += String.fromCharCode(msg.getBitWord(i * 8 + 32, 8));
                }

                cubeEvents.push({
                    type: "HARDWARE",
                    timestamp: timestamp,
                    hardwareName: hardwareName,
                    hardwareVersion: `${hwMajor}.${hwMinor}`,
                    softwareVersion: `${swMajor}.${swMinor}`,
                    gyroSupported: false
                });
            } else if (eventType == 0x10) { // BATTERY
                let batteryLevel = msg.getBitWord(24, 8);

                cubeEvents.push({
                    type: "BATTERY",
                    timestamp: timestamp,
                    batteryLevel: Math.min(batteryLevel, 100)
                });
            } else if (eventType == 0x11) { // DISCONNECT
                conn.disconnect();
            }
        }

        return cubeEvents;
    }
}

/**
 * Driver implementation for GAN Gen4 protocol, supported cubes:
 *  - GAN12 ui Maglev
 *  - GAN14 ui FreePlay
 */
class GanGen4ProtocolDriver {
    constructor() {
        this.serial = -1;
        this.lastSerial = -1;
        this.lastLocalTimestamp = null;
        this.moveBuffer = [];
        this.hwInfo = {};
    }

    createCommandMessage(command) {
        let msg = new Uint8Array(20).fill(0);
        switch (command.type) {
            case 'REQUEST_FACELETS':
                msg.set([0xDD, 0x04, 0x00, 0xED, 0x00, 0x00]);
                break;
            case 'REQUEST_HARDWARE':
                this.hwInfo = {};
                msg.set([0xDF, 0x03, 0x00, 0x00, 0x00]);
                break;
            case 'REQUEST_BATTERY':
                msg.set([0xDD, 0x04, 0x00, 0xEF, 0x00, 0x00]);
                break;
            case 'REQUEST_RESET':
                msg.set([0xD2, 0x0D, 0x05, 0x39, 0x77, 0x00, 0x00, 0x01, 0x23, 0x45, 0x67, 0x89, 0xAB, 0x00, 0x00, 0x00]);
                break;
            default:
                msg = undefined;
        }
        return msg;
    }

    async handleStateEvent(conn, eventMessage) {
        const timestamp = now();
        const cubeEvents = [];
        const msg = new GanProtocolMessageView(eventMessage);

        const eventType = msg.getBitWord(0, 8);
        const dataLength = msg.getBitWord(8, 8);

        if (eventType == 0x01) { // MOVE
            if (this.lastSerial != -1) {
                this.lastLocalTimestamp = timestamp;
                let cubeTimestamp = msg.getBitWord(16, 32, true);
                let serial = this.serial = msg.getBitWord(48, 16, true);

                let direction = msg.getBitWord(64, 2);
                let face = [2, 32, 8, 1, 16, 4].indexOf(msg.getBitWord(66, 6));
                let move = "URFDLB".charAt(face) + " '".charAt(direction);

                if (face >= 0) {
                    cubeEvents.push({
                        type: "MOVE",
                        serial: serial,
                        timestamp: timestamp,
                        localTimestamp: timestamp,
                        cubeTimestamp: cubeTimestamp,
                        face: face,
                        direction: direction,
                        move: move.trim()
                    });
                }
            }
        } else if (eventType == 0xED) { // FACELETS
            let serial = this.serial = msg.getBitWord(16, 16, true);

            if (this.lastSerial == -1)
                this.lastSerial = serial;

            // Corner/Edge Permutation/Orientation
            let cp = [];
            let co = [];
            let ep = [];
            let eo = [];

            // Corners
            for (let i = 0; i < 7; i++) {
                cp.push(msg.getBitWord(32 + i * 3, 3));
                co.push(msg.getBitWord(53 + i * 2, 2));
            }
            cp.push(28 - sum(cp));
            co.push((3 - (sum(co) % 3)) % 3);

            // Edges
            for (let i = 0; i < 11; i++) {
                ep.push(msg.getBitWord(69 + i * 4, 4));
                eo.push(msg.getBitWord(113 + i, 1));
            }
            ep.push(66 - sum(ep));
            eo.push((2 - (sum(eo) % 2)) % 2);

            cubeEvents.push({
                type: "FACELETS",
                serial: serial,
                timestamp: timestamp,
                facelets: toKociembaFacelets(cp, co, ep, eo),
                state: {
                    CP: cp,
                    CO: co,
                    EP: ep,
                    EO: eo
                },
            });
        } else if (eventType == 0xEC) { // GYRO
            // Orientation Quaternion
            let qw = msg.getBitWord(16, 16);
            let qx = msg.getBitWord(32, 16);
            let qy = msg.getBitWord(48, 16);
            let qz = msg.getBitWord(64, 16);

            // Angular Velocity
            let vx = msg.getBitWord(80, 4);
            let vy = msg.getBitWord(84, 4);
            let vz = msg.getBitWord(88, 4);

            cubeEvents.push({
                type: "GYRO",
                timestamp: timestamp,
                quaternion: {
                    x: (1 - (qx >> 15) * 2) * (qx & 0x7FFF) / 0x7FFF,
                    y: (1 - (qy >> 15) * 2) * (qy & 0x7FFF) / 0x7FFF,
                    z: (1 - (qz >> 15) * 2) * (qz & 0x7FFF) / 0x7FFF,
                    w: (1 - (qw >> 15) * 2) * (qw & 0x7FFF) / 0x7FFF
                },
                velocity: {
                    x: (1 - (vx >> 3) * 2) * (vx & 0x7),
                    y: (1 - (vy >> 3) * 2) * (vy & 0x7),
                    z: (1 - (vz >> 3) * 2) * (vz & 0x7)
                }
            });
        } else if (eventType == 0xEF) { // BATTERY
            let batteryLevel = msg.getBitWord(8 + dataLength * 8, 8);

            cubeEvents.push({
                type: "BATTERY",
                timestamp: timestamp,
                batteryLevel: Math.min(batteryLevel, 100)
            });
        } else if (eventType == 0xEA) { // DISCONNECT
            conn.disconnect();
        }

        return cubeEvents;
    }
}

module.exports = {
    GanGen2ProtocolDriver,
    GanGen3ProtocolDriver,
    GanGen4ProtocolDriver,
    GanProtocolMessageView
};