const WebSocket = require('ws');

/**
 * Input bridge that connects native cube events to the existing Python gaming input system
 */
class InputBridge {
    constructor() {
        this.server = null;
        this.connectedClients = new Set();
        this.port = 8082;
        
        // Gaming input configuration
        this.moveMapping = {
            'R': { type: 'gamepad', action: 'R1', description: 'Right Bumper' },
            "R'": { type: 'gamepad', action: 'R2', description: 'Right Trigger' },
            'L': { type: 'gamepad', action: 'B', description: 'B Button' },
            "L'": { type: 'gamepad', action: 'B', description: 'B Button' },
            'D': { type: 'gamepad', action: 'X', description: 'X Button' },
            'B': { type: 'gamepad', action: 'R3', description: 'Right Stick Press' },
            'F': { type: 'gamepad', action: 'DPAD_RIGHT', description: 'D-Pad Right' },
            "F'": { type: 'gamepad', action: 'DPAD_LEFT', description: 'D-Pad Left' },
            'U': { type: 'gamepad', action: 'Y', description: 'Y Button' },
            "U'": { type: 'gamepad', action: 'Y', description: 'Y Button' }
        };

        // Orientation processing state
        this.orientationState = {
            referenceOrientation: null,
            lastProcessTime: 0,
            rateLimitMs: 16 // ~60 FPS max
        };
    }

    /**
     * Start the input bridge WebSocket server
     */
    async start() {
        return new Promise((resolve, reject) => {
            try {
                this.server = new WebSocket.Server({ port: this.port });
                
                this.server.on('connection', (ws, request) => {
                    const clientAddress = request.connection.remoteAddress;
                    console.log(`[Input Bridge] Client connected from ${clientAddress}`);
                    
                    this.connectedClients.add(ws);
                    
                    // Send welcome message with capabilities
                    this.sendToClient(ws, {
                        type: 'BRIDGE_CONNECTED',
                        capabilities: {
                            gamepadEmulation: true,
                            keyboardInput: true,
                            mouseInput: true,
                            orientationControl: true
                        },
                        moveMapping: this.moveMapping
                    });
                    
                    ws.on('message', (message) => {
                        try {
                            const data = JSON.parse(message.toString());
                            this.handleClientMessage(ws, data);
                        } catch (error) {
                            console.error('[Input Bridge] Error parsing client message:', error);
                        }
                    });
                    
                    ws.on('close', () => {
                        console.log(`[Input Bridge] Client disconnected from ${clientAddress}`);
                        this.connectedClients.delete(ws);
                    });
                    
                    ws.on('error', (error) => {
                        console.error('[Input Bridge] Client WebSocket error:', error);
                        this.connectedClients.delete(ws);
                    });
                });
                
                this.server.on('listening', () => {
                    console.log(`[Input Bridge] Server listening on port ${this.port}`);
                    resolve();
                });
                
                this.server.on('error', (error) => {
                    console.error('[Input Bridge] Server error:', error);
                    reject(error);
                });
                
            } catch (error) {
                reject(error);
            }
        });
    }

    /**
     * Handle messages from connected clients (like dashboard or Python bridge)
     */
    handleClientMessage(ws, data) {
        switch (data.type) {
            case 'PING':
                this.sendToClient(ws, { type: 'PONG', timestamp: Date.now() });
                break;
                
            case 'GET_STATUS':
                this.sendToClient(ws, {
                    type: 'STATUS',
                    connectedClients: this.connectedClients.size,
                    moveMapping: this.moveMapping,
                    uptime: process.uptime()
                });
                break;
                
            case 'RESET_ORIENTATION':
                this.resetOrientation();
                this.broadcast({
                    type: 'ORIENTATION_RESET',
                    timestamp: Date.now()
                });
                break;
                
            default:
                console.log(`[Input Bridge] Unknown message type: ${data.type}`);
        }
    }

    /**
     * Process cube move events for gaming input
     */
    processCubeMove(moveEvent) {
        const mapping = this.moveMapping[moveEvent.move];
        
        if (!mapping) {
            console.log(`[Input Bridge] No mapping for move: ${moveEvent.move}`);
            return;
        }

        console.log(`[Input Bridge] Move: ${moveEvent.move} → ${mapping.description}`);
        
        // Broadcast to all connected clients (Python bridge, dashboard, etc.)
        this.broadcast({
            type: 'MOVE',
            move: moveEvent.move,
            mapping: mapping,
            cubeTimestamp: moveEvent.cubeTimestamp,
            localTimestamp: moveEvent.localTimestamp,
            timestamp: Date.now()
        });
    }

    /**
     * Process cube orientation events for analog control
     */
    processOrientation(gyroEvent) {
        const now = Date.now();
        
        // Rate limiting to prevent overwhelming the gaming system
        if (now - this.orientationState.lastProcessTime < this.orientationState.rateLimitMs) {
            return;
        }
        
        this.orientationState.lastProcessTime = now;
        
        // Calculate relative orientation from reference point
        const tiltData = this.calculateTiltFromQuaternion(gyroEvent.quaternion);
        
        if (tiltData) {
            // Broadcast orientation data for analog control
            this.broadcast({
                type: 'ORIENTATION',
                tiltX: tiltData.tiltX,
                tiltY: tiltData.tiltY,
                spinZ: tiltData.spinZ,
                rawQuaternion: gyroEvent.quaternion,
                velocity: gyroEvent.velocity,
                timestamp: Date.now()
            });
        }
    }

    /**
     * Calculate tilt values from quaternion for gaming control
     */
    calculateTiltFromQuaternion(quaternion) {
        // Set reference orientation on first reading
        if (!this.orientationState.referenceOrientation) {
            this.orientationState.referenceOrientation = { ...quaternion };
            console.log('[Input Bridge] Reference orientation set for analog control');
            return null;
        }

        // Calculate relative quaternion (simplified approach for gaming)
        // In a full implementation, this would use proper quaternion math
        const ref = this.orientationState.referenceOrientation;
        
        // Simplified tilt calculation based on quaternion differences
        const deltaX = quaternion.x - ref.x;
        const deltaY = quaternion.y - ref.y;
        const deltaZ = quaternion.z - ref.z;
        
        // Map to gaming controls with appropriate scaling and deadzones
        let tiltX = Math.max(-1.0, Math.min(1.0, deltaZ * -4.0)); // Forward/back
        let tiltY = Math.max(-1.0, Math.min(1.0, deltaX * -4.0)); // Left/right
        let spinZ = Math.max(-1.0, Math.min(1.0, deltaY * -1.5)); // Rotation
        
        // Apply deadzone
        const deadzone = 0.1;
        if (Math.abs(tiltX) < deadzone) tiltX = 0;
        if (Math.abs(tiltY) < deadzone) tiltY = 0;
        if (Math.abs(spinZ) < deadzone) spinZ = 0;
        
        return { tiltX, tiltY, spinZ };
    }

    /**
     * Reset orientation reference point
     */
    resetOrientation() {
        this.orientationState.referenceOrientation = null;
        console.log('[Input Bridge] Orientation reference reset');
    }

    /**
     * Send message to a specific client
     */
    sendToClient(ws, message) {
        if (ws.readyState === WebSocket.OPEN) {
            try {
                ws.send(JSON.stringify(message));
            } catch (error) {
                console.error('[Input Bridge] Error sending to client:', error);
                this.connectedClients.delete(ws);
            }
        }
    }

    /**
     * Broadcast message to all connected clients
     */
    broadcast(message) {
        const messageStr = JSON.stringify(message);
        
        this.connectedClients.forEach(ws => {
            if (ws.readyState === WebSocket.OPEN) {
                try {
                    ws.send(messageStr);
                } catch (error) {
                    console.error('[Input Bridge] Error broadcasting to client:', error);
                    this.connectedClients.delete(ws);
                }
            } else {
                this.connectedClients.delete(ws);
            }
        });
    }

    /**
     * Get bridge statistics
     */
    getStats() {
        return {
            port: this.port,
            connectedClients: this.connectedClients.size,
            uptime: process.uptime(),
            mappings: Object.keys(this.moveMapping).length,
            hasReference: this.orientationState.referenceOrientation !== null
        };
    }

    /**
     * Stop the input bridge server
     */
    async stop() {
        return new Promise((resolve) => {
            if (this.server) {
                // Close all client connections
                this.connectedClients.forEach(ws => {
                    try {
                        ws.close(1000, 'Server shutting down');
                    } catch (error) {
                        // Ignore errors when closing
                    }
                });
                
                // Close server
                this.server.close(() => {
                    console.log('[Input Bridge] Server stopped');
                    resolve();
                });
            } else {
                resolve();
            }
        });
    }
}

module.exports = { InputBridge };