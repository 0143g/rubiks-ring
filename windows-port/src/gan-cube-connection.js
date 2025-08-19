const noble = require('@stoprocent/noble');
const { EventEmitter } = require('events');
const { GanGen2CubeEncrypter, GanGen3CubeEncrypter, GanGen4CubeEncrypter } = require('./gan-cube-encrypter');
const { GanGen2ProtocolDriver, GanGen3ProtocolDriver, GanGen4ProtocolDriver } = require('./gan-cube-protocol');
const { 
    GAN_GEN2_SERVICE, GAN_GEN2_COMMAND_CHARACTERISTIC, GAN_GEN2_STATE_CHARACTERISTIC,
    GAN_GEN3_SERVICE, GAN_GEN3_COMMAND_CHARACTERISTIC, GAN_GEN3_STATE_CHARACTERISTIC,
    GAN_GEN4_SERVICE, GAN_GEN4_COMMAND_CHARACTERISTIC, GAN_GEN4_STATE_CHARACTERISTIC,
    GAN_ENCRYPTION_KEYS, GAN_CIC_LIST
} = require('./gan-cube-definitions');

/**
 * Native Bluetooth connection manager for GAN Smart Cubes using noble
 */
class GanCubeConnection extends EventEmitter {
    constructor() {
        super();
        this.peripheral = null;
        this.encrypter = null;
        this.driver = null;
        this.commandCharacteristic = null;
        this.stateCharacteristic = null;
        this.isConnected = false;
        this.deviceName = null;
        this.deviceMAC = null;
        this.generation = null;
        this._discoveredPeripherals = new Map();
        this._scanRestartInterval = null;
        
        this.setupNobleEvents();
    }

    setupNobleEvents() {
        noble.on('stateChange', (state) => {
            console.log(`[GAN Cube] Bluetooth adapter state: ${state}`);
            if (state === 'poweredOn') {
                this.emit('bluetoothReady');
            } else {
                this.emit('bluetoothError', new Error(`Bluetooth not ready: ${state}`));
            }
        });

        noble.on('discover', (peripheral) => {
            const localName = peripheral.advertisement.localName || '';
            const serviceUuids = peripheral.advertisement.serviceUuids || [];
            const manufacturerData = peripheral.advertisement.manufacturerData;
            
            // Debug: Log all discovered devices to help troubleshoot
            if (localName) {
                console.log(`[GAN Cube] Named device: "${localName}" | ${peripheral.address} | ${peripheral.rssi}dBm`);
            }
            
            // More comprehensive GAN cube detection 
            // Check name patterns - must include "gan", "moyu", "i3", "356", etc.
            // Also check for specific patterns like "GANi39Jl" 
            const lowerName = localName.toLowerCase();
            const namePatterns = ['gan', 'moyu', 'i3', '356', 'i carry', 'ui', 'maglev'];
            const isGanByName = namePatterns.some(pattern => lowerName.includes(pattern)) ||
                                /^gan[a-z0-9]+/i.test(localName); // Matches GANi39Jl, GAN356, etc.
            
            // Check for GAN-specific service UUIDs (must match exactly)
            const isGanByService = serviceUuids.some(uuid => {
                const u = uuid.toLowerCase().replace(/-/g, '');
                // Check for exact GAN service UUIDs
                return u === '6e400001b5a3f393e0a9e50e24dc4179' || // Gen2 service
                       u === '8653000a43e647b79cb05fc21d4ae340' || // Gen3 service  
                       u === '000000100000fff7fff6fff5fff4fff0';    // Gen4 service
            });
            
            // Also check manufacturer data for GAN company codes
            let isGanByManufacturer = false;
            if (manufacturerData && manufacturerData.length >= 2) {
                const companyId = manufacturerData.readUInt16LE(0);
                // GAN uses various company IDs, check against known list
                isGanByManufacturer = (companyId & 0xFF01) === 0x0001; // Common GAN pattern
            }
            
            const isGanCube = isGanByName || isGanByService || isGanByManufacturer;
            
            if (isGanCube) {
                console.log(`[GAN Cube] 🎲 FOUND GAN CUBE: "${localName}" | ${peripheral.address} | ${peripheral.rssi}dBm`);
                if (serviceUuids.length > 0) {
                    console.log(`[GAN Cube]    Services: ${serviceUuids.join(', ')}`);
                }
                
                // Store peripheral reference internally for connection
                this._discoveredPeripherals = this._discoveredPeripherals || new Map();
                this._discoveredPeripherals.set(peripheral.address, peripheral);
                
                this.emit('cubeFound', {
                    name: localName || 'GAN Cube',
                    address: peripheral.address,
                    rssi: peripheral.rssi
                });
            }
            
            // DO NOT connect to unnamed devices - they're usually not cubes!
            // This was causing false positives with headphones, speakers, etc.
            // Only log them for debugging purposes
            if (!localName && !isGanCube && (peripheral.rssi > -60)) {
                console.log(`[GAN Cube] Strong unnamed device (NOT connecting): ${peripheral.address} | ${peripheral.rssi}dBm`);
                // DO NOT emit cubeFound for unnamed devices - they're not cubes!
            }
        });

        noble.on('scanStart', () => {
            console.log('[GAN Cube] Started scanning for cubes...');
        });

        noble.on('scanStop', () => {
            console.log('[GAN Cube] Stopped scanning for cubes');
        });
    }

    /**
     * Initialize Bluetooth and start scanning
     */
    async initialize() {
        return new Promise((resolve, reject) => {
            if (noble.state === 'poweredOn') {
                resolve();
            } else {
                const timeout = setTimeout(() => {
                    reject(new Error('Bluetooth initialization timeout'));
                }, 10000);

                this.once('bluetoothReady', () => {
                    clearTimeout(timeout);
                    resolve();
                });

                this.once('bluetoothError', (error) => {
                    clearTimeout(timeout);
                    reject(error);
                });
            }
        });
    }

    /**
     * Start scanning for GAN cubes
     */
    startScanning() {
        if (noble.state !== 'poweredOn') {
            throw new Error('Bluetooth not ready');
        }
        
        console.log('[GAN Cube] 🔍 Starting MAXIMUM AGGRESSIVE scan...');
        console.log('[GAN Cube] Scanning ALL devices with duplicates enabled...');
        
        // Ultra-aggressive approach: scan everything with duplicates
        noble.startScanning([], true);
        
        // Restart scanning periodically to catch devices that might not be advertising
        const restartInterval = setInterval(() => {
            console.log('[GAN Cube] 🔄 Restarting scan to catch new advertisements...');
            noble.stopScanning();
            setTimeout(() => {
                if (noble.state === 'poweredOn') {
                    noble.startScanning([], true);
                    console.log('[GAN Cube] Scan restarted');
                }
            }, 500); // Increased delay for Windows Bluetooth stability
        }, 3000); // More frequent restarts to catch intermittent advertising
        
        // Store interval so we can clear it when stopping
        this._scanRestartInterval = restartInterval;
    }

    /**
     * Stop scanning for cubes
     */
    stopScanning() {
        console.log('[GAN Cube] 🛑 Stopping scan...');
        if (this._scanRestartInterval) {
            clearInterval(this._scanRestartInterval);
            this._scanRestartInterval = null;
        }
        noble.stopScanning();
    }

    /**
     * Connect to a specific cube by address
     */
    async connectToCube(address) {
        return new Promise(async (resolve, reject) => {
            try {
                // Find the peripheral
                const peripheral = await this.findPeripheralByAddress(address);
                if (!peripheral) {
                    reject(new Error(`Cube with address ${address} not found`));
                    return;
                }

                await this.connectToPeripheral(peripheral);
                resolve();
            } catch (error) {
                reject(error);
            }
        });
    }

    /**
     * Connect to the first available GAN cube
     */
    async connectToFirstAvailableCube() {
        // HARDCODED: Connect directly to the user's specific GAN cube
        const TARGET_CUBE_ADDRESS = 'ab:12:34:62:bc:15';
        const TARGET_CUBE_NAME = 'GANi39Jl';
        
        console.log(`[GAN Cube] 🎯 HARDCODED: Looking specifically for ${TARGET_CUBE_NAME} at ${TARGET_CUBE_ADDRESS}`);
        console.log('[GAN Cube] Make sure your cube is charged and nearby');
        console.log('[GAN Cube] Try twisting the cube a few times to wake it up');
        
        return new Promise((resolve, reject) => {
            const timeout = setTimeout(() => {
                this.stopScanning();
                console.log(`[GAN Cube] ❌ Could not find ${TARGET_CUBE_NAME} at ${TARGET_CUBE_ADDRESS}`);
                reject(new Error(`Could not find ${TARGET_CUBE_NAME} at ${TARGET_CUBE_ADDRESS}. Make sure cube is charged and advertising.`));
            }, 30000);

            const onDiscover = async (peripheral) => {
                // ONLY connect to the exact cube we want
                if (peripheral.address.toLowerCase() === TARGET_CUBE_ADDRESS.toLowerCase()) {
                    console.log(`[GAN Cube] 🎲 FOUND TARGET CUBE: ${TARGET_CUBE_NAME} at ${TARGET_CUBE_ADDRESS}!`);
                    clearTimeout(timeout);
                    this.stopScanning();
                    noble.removeListener('discover', onDiscover);
                    
                    try {
                        await this.connectToPeripheral(peripheral);
                        resolve();
                    } catch (error) {
                        console.error('[GAN Cube] ❌ Connection to target cube failed:', error.message);
                        reject(error);
                    }
                }
            };

            noble.on('discover', onDiscover);
            this.startScanning();
        });
    }

    /**
     * Find peripheral by Bluetooth address
     */
    async findPeripheralByAddress(address) {
        return new Promise((resolve) => {
            console.log(`[GAN Cube] Looking for cube with address: ${address}`);
            let found = false;
            const timeout = setTimeout(() => {
                if (!found) {
                    console.log(`[GAN Cube] ❌ Could not find cube with address: ${address}`);
                    this.stopScanning();
                    resolve(null);
                }
            }, 20000); // Increased timeout

            const onDiscover = (peripheral) => {
                console.log(`[GAN Cube] Checking device: ${peripheral.address} vs ${address}`);
                if (peripheral.address.toLowerCase() === address.toLowerCase()) {
                    console.log(`[GAN Cube] ✅ Found target cube: ${address}`);
                    found = true;
                    clearTimeout(timeout);
                    this.stopScanning();
                    noble.removeListener('discover', onDiscover);
                    
                    // Store in cache for later use
                    this._discoveredPeripherals = this._discoveredPeripherals || new Map();
                    this._discoveredPeripherals.set(peripheral.address, peripheral);
                    
                    resolve(peripheral);
                }
            };

            noble.on('discover', onDiscover);
            this.startScanning();
        });
    }

    /**
     * Connect to peripheral with retry logic to handle Windows Bluetooth flakiness
     */
    async connectWithRetry(peripheral, maxRetries = 3) {
        for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                console.log(`[GAN Cube] Connection attempt ${attempt}/${maxRetries}...`);
                
                await new Promise((resolve, reject) => {
                    // Set a timeout for the connection attempt
                    const timeout = setTimeout(() => {
                        reject(new Error('Connection timeout (10s)'));
                    }, 10000);
                    
                    peripheral.connect((error) => {
                        clearTimeout(timeout);
                        // In noble, undefined/null means success, any actual error object means failure
                        if (error !== null && error !== undefined) {
                            const errorMsg = error?.message || error?.toString() || 'Unknown connection error';
                            reject(new Error(`Connection failed: ${errorMsg}`));
                        } else {
                            // Success - error is null or undefined
                            console.log(`[GAN Cube] ✅ Connect callback successful (error: ${error})`);
                            resolve();
                        }
                    });
                });
                
                // Success!
                console.log(`[GAN Cube] ✅ Connected on attempt ${attempt}`);
                return;
                
            } catch (error) {
                console.log(`[GAN Cube] ❌ Attempt ${attempt} failed: ${error.message}`);
                
                if (attempt === maxRetries) {
                    throw new Error(`Failed to connect after ${maxRetries} attempts. Last error: ${error.message}`);
                }
                
                // Wait before retry with exponential backoff
                const delay = attempt * 2000; // 2s, 4s, 6s...
                console.log(`[GAN Cube] Waiting ${delay}ms before retry...`);
                await new Promise(resolve => setTimeout(resolve, delay));
            }
        }
    }

    /**
     * Connect to a specific peripheral and set up encryption/protocol
     */
    async connectToPeripheral(peripheral) {
        try {
            this.peripheral = peripheral;
            this.deviceName = peripheral.advertisement.localName || 'GAN-XXXX';
            this.deviceMAC = peripheral.address;

            console.log(`[GAN Cube] Connecting to ${this.deviceName} (${this.deviceMAC})`);

            // Connect to peripheral with retry logic
            await this.connectWithRetry(peripheral, 3);

            console.log(`[GAN Cube] Connected to ${this.deviceName}`);

            // Discover services and characteristics
            const { services, characteristics } = await this.discoverServicesAndCharacteristics(peripheral);
            
            // Determine cube generation and set up protocol
            this.setupProtocolAndEncryption(services, characteristics);

            // Set up characteristic notifications
            await this.setupCharacteristicNotifications();

            // Set up disconnect handler
            peripheral.on('disconnect', () => {
                console.log(`[GAN Cube] Disconnected from ${this.deviceName}`);
                this.handleDisconnect();
            });

            this.isConnected = true;
            this.emit('connected', {
                deviceName: this.deviceName,
                deviceMAC: this.deviceMAC,
                generation: this.generation
            });

            // Request initial cube state
            setTimeout(() => {
                if (this.isConnected && this.peripheral && this.peripheral.state === 'connected') {
                    this.sendCubeCommand({ type: 'REQUEST_FACELETS' });
                    this.sendCubeCommand({ type: 'REQUEST_HARDWARE' });
                    this.sendCubeCommand({ type: 'REQUEST_BATTERY' });
                } else {
                    console.log('[GAN Cube] Skipping initial state requests - cube disconnected');
                }
            }, 1000);

        } catch (error) {
            console.error(`[GAN Cube] Connection failed: ${error.message}`);
            throw error;
        }
    }

    /**
     * Discover services and characteristics
     */
    async discoverServicesAndCharacteristics(peripheral) {
        return new Promise((resolve, reject) => {
            peripheral.discoverServices([], (error, services) => {
                if (error) {
                    reject(new Error(`Service discovery failed: ${error.message}`));
                    return;
                }

                const promises = services.map(service => {
                    return new Promise((serviceResolve, serviceReject) => {
                        service.discoverCharacteristics([], (charError, characteristics) => {
                            if (charError) {
                                serviceReject(charError);
                            } else {
                                serviceResolve({ service, characteristics });
                            }
                        });
                    });
                });

                Promise.all(promises).then(results => {
                    resolve({ 
                        services,
                        characteristics: results.reduce((acc, result) => {
                            acc[result.service.uuid] = result.characteristics;
                            return acc;
                        }, {})
                    });
                }).catch(reject);
            });
        });
    }

    /**
     * Set up protocol and encryption based on discovered services
     */
    setupProtocolAndEncryption(services, characteristics) {
        let serviceUuid = null;
        let commandCharUuid = null;
        let stateCharUuid = null;

        // Detect cube generation based on services
        for (const service of services) {
            const uuid = service.uuid;
            
            if (uuid === GAN_GEN2_SERVICE.replace(/-/g, '')) {
                this.generation = 'Gen2';
                serviceUuid = uuid;
                commandCharUuid = GAN_GEN2_COMMAND_CHARACTERISTIC.replace(/-/g, '');
                stateCharUuid = GAN_GEN2_STATE_CHARACTERISTIC.replace(/-/g, '');
                this.driver = new GanGen2ProtocolDriver();
                break;
            } else if (uuid === GAN_GEN3_SERVICE.replace(/-/g, '')) {
                this.generation = 'Gen3';
                serviceUuid = uuid;
                commandCharUuid = GAN_GEN3_COMMAND_CHARACTERISTIC.replace(/-/g, '');
                stateCharUuid = GAN_GEN3_STATE_CHARACTERISTIC.replace(/-/g, '');
                this.driver = new GanGen3ProtocolDriver();
                break;
            } else if (uuid === GAN_GEN4_SERVICE.replace(/-/g, '')) {
                this.generation = 'Gen4';
                serviceUuid = uuid;
                commandCharUuid = GAN_GEN4_COMMAND_CHARACTERISTIC.replace(/-/g, '');
                stateCharUuid = GAN_GEN4_STATE_CHARACTERISTIC.replace(/-/g, '');
                this.driver = new GanGen4ProtocolDriver();
                break;
            }
        }

        if (!this.generation) {
            throw new Error('Unknown cube generation - no matching service found');
        }

        // Find characteristics
        const serviceChars = characteristics[serviceUuid];
        if (!serviceChars) {
            throw new Error(`No characteristics found for service ${serviceUuid}`);
        }

        this.commandCharacteristic = serviceChars.find(char => char.uuid === commandCharUuid);
        this.stateCharacteristic = serviceChars.find(char => char.uuid === stateCharUuid);

        if (!this.commandCharacteristic || !this.stateCharacteristic) {
            throw new Error('Required characteristics not found');
        }

        // Set up encryption
        this.setupEncryption();

        console.log(`[GAN Cube] Detected ${this.generation} cube with MAC: ${this.deviceMAC}`);
    }

    /**
     * Set up AES encryption with device MAC address
     */
    setupEncryption() {
        // Extract MAC address bytes for salt
        const macBytes = this.deviceMAC.split(':').map(hex => parseInt(hex, 16));
        const salt = new Uint8Array(macBytes);

        // Try each encryption key until we find one that works
        for (const keyData of GAN_ENCRYPTION_KEYS) {
            const key = new Uint8Array(keyData.key);
            const iv = new Uint8Array(keyData.iv);

            try {
                switch (this.generation) {
                    case 'Gen2':
                        this.encrypter = new GanGen2CubeEncrypter(key, iv, salt);
                        break;
                    case 'Gen3':
                        this.encrypter = new GanGen3CubeEncrypter(key, iv, salt);
                        break;
                    case 'Gen4':
                        this.encrypter = new GanGen4CubeEncrypter(key, iv, salt);
                        break;
                }
                
                console.log(`[GAN Cube] Encryption initialized for ${this.generation}`);
                return;
            } catch (error) {
                console.warn(`[GAN Cube] Failed to initialize encryption with key: ${error.message}`);
            }
        }

        throw new Error('Failed to initialize encryption with any available key');
    }

    /**
     * Set up characteristic notifications
     */
    async setupCharacteristicNotifications() {
        return new Promise((resolve, reject) => {
            this.stateCharacteristic.on('data', (data, isNotification) => {
                if (isNotification) {
                    this.handleStateUpdate(data);
                }
            });

            this.stateCharacteristic.subscribe((error) => {
                if (error) {
                    reject(new Error(`Failed to subscribe to notifications: ${error.message}`));
                } else {
                    console.log('[GAN Cube] Subscribed to state notifications');
                    resolve();
                }
            });
        });
    }

    /**
     * Handle incoming state updates from cube
     */
    async handleStateUpdate(data) {
        try {
            if (data && data.length >= 16) {
                console.log(`[GAN Cube] Raw data received: ${data.length} bytes`);
                const decryptedMessage = this.encrypter.decrypt(new Uint8Array(data));
                console.log(`[GAN Cube] Decrypted message: ${decryptedMessage.length} bytes, first 4 bytes: [${Array.from(decryptedMessage.slice(0, 4)).map(b => b.toString(16).padStart(2, '0')).join(', ')}]`);
                
                const cubeEvents = await this.driver.handleStateEvent(this, decryptedMessage);
                console.log(`[GAN Cube] Generated ${cubeEvents.length} events`);
                
                cubeEvents.forEach(event => {
                    this.emit('cubeEvent', event);
                    this.emit(event.type.toLowerCase(), event);
                });
            } else {
                console.warn(`[GAN Cube] Invalid data received: ${data ? data.length : 0} bytes (minimum 16 required)`);
            }
        } catch (error) {
            console.error(`[GAN Cube] Error handling state update: ${error.message}`);
            console.error(`[GAN Cube] Stack trace:`, error.stack);
            // Don't disconnect on protocol errors - just log them
        }
    }

    /**
     * Send command to cube
     */
    async sendCubeCommand(command) {
        if (!this.isConnected || !this.driver) {
            throw new Error('Cube not connected');
        }

        try {
            const commandMessage = this.driver.createCommandMessage(command);
            if (commandMessage) {
                await this.sendCommandMessage(commandMessage);
            }
        } catch (error) {
            console.error(`[GAN Cube] Error sending command: ${error.message}`);
            throw error;
        }
    }

    /**
     * Send raw command message to cube
     */
    async sendCommandMessage(message) {
        if (!this.commandCharacteristic || !this.encrypter) {
            throw new Error('Cube not properly initialized');
        }

        const encryptedMessage = this.encrypter.encrypt(message);
        
        return new Promise((resolve, reject) => {
            this.commandCharacteristic.write(Buffer.from(encryptedMessage), false, (error) => {
                if (error) {
                    reject(new Error(`Failed to write command: ${error.message}`));
                } else {
                    resolve();
                }
            });
        });
    }

    /**
     * Handle cube disconnection
     */
    handleDisconnect() {
        this.isConnected = false;
        this.peripheral = null;
        this.commandCharacteristic = null;
        this.stateCharacteristic = null;
        this.encrypter = null;
        this.driver = null;
        
        this.emit('disconnected');
        this.emit('cubeEvent', { 
            type: 'DISCONNECT',
            timestamp: Date.now()
        });
    }

    /**
     * Manually disconnect from cube
     */
    async disconnect() {
        if (this.peripheral && this.isConnected) {
            return new Promise((resolve) => {
                this.peripheral.disconnect((error) => {
                    if (error) {
                        console.warn(`[GAN Cube] Disconnect error: ${error.message}`);
                    }
                    this.handleDisconnect();
                    resolve();
                });
            });
        }
    }

    /**
     * Get connection status
     */
    getConnectionInfo() {
        return {
            isConnected: this.isConnected,
            deviceName: this.deviceName,
            deviceMAC: this.deviceMAC,
            generation: this.generation
        };
    }
}

module.exports = { GanCubeConnection };