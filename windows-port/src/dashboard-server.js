const express = require('express');
const WebSocket = require('ws');
const path = require('path');
const { GanCubeConnection } = require('./gan-cube-connection');

/**
 * Dashboard server providing web interface and WebSocket API for cube management
 */
class DashboardServer {
    constructor() {
        this.app = express();
        this.httpServer = null;
        this.wss = null;
        this.cubeConnection = null;
        this.connectedClients = new Set();
        this.port = 3000;
        this.wsPort = 8080;
        
        this.setupExpress();
        this.setupWebSocket();
    }

    /**
     * Set up Express HTTP server for serving dashboard files
     */
    setupExpress() {
        // Serve static files from dashboard directory
        this.app.use(express.static(path.join(__dirname, '../dashboard')));
        
        // API endpoint for connection status
        this.app.get('/api/status', (req, res) => {
            const status = this.cubeConnection ? this.cubeConnection.getConnectionInfo() : {
                isConnected: false,
                deviceName: null,
                deviceMAC: null,
                generation: null
            };
            
            res.json({
                cube: status,
                server: {
                    uptime: process.uptime(),
                    connectedClients: this.connectedClients.size,
                    timestamp: Date.now()
                }
            });
        });

        // API endpoint for available cubes (if scanning)
        this.app.get('/api/cubes', (req, res) => {
            // This would require implementing a cube discovery service
            res.json({ message: 'Cube discovery not implemented in HTTP API. Use WebSocket interface.' });
        });

        // Health check endpoint
        this.app.get('/health', (req, res) => {
            res.json({ status: 'OK', timestamp: Date.now() });
        });
    }

    /**
     * Set up WebSocket server for real-time communication
     */
    setupWebSocket() {
        this.wss = new WebSocket.Server({ port: this.wsPort });
        
        this.wss.on('connection', (ws) => {
            console.log('[Dashboard] New WebSocket client connected');
            this.connectedClients.add(ws);
            
            // Send initial connection status
            this.sendToClient(ws, {
                type: 'CONNECTION_STATUS',
                connected: this.cubeConnection ? this.cubeConnection.getConnectionInfo().isConnected : false,
                cubeInfo: this.cubeConnection ? this.cubeConnection.getConnectionInfo() : null
            });

            ws.on('message', async (message) => {
                try {
                    const data = JSON.parse(message.toString());
                    await this.handleWebSocketMessage(ws, data);
                } catch (error) {
                    console.error('[Dashboard] Error handling WebSocket message:', error);
                    this.sendToClient(ws, {
                        type: 'ERROR',
                        message: error.message
                    });
                }
            });

            ws.on('close', () => {
                console.log('[Dashboard] WebSocket client disconnected');
                this.connectedClients.delete(ws);
            });

            ws.on('error', (error) => {
                console.error('[Dashboard] WebSocket error:', error);
                this.connectedClients.delete(ws);
            });
        });

        console.log(`[Dashboard] WebSocket server listening on port ${this.wsPort}`);
    }

    /**
     * Handle incoming WebSocket messages
     */
    async handleWebSocketMessage(ws, data) {
        console.log('[Dashboard] Received WebSocket message:', data.type);
        
        switch (data.type) {
            case 'CONNECT_CUBE':
                await this.handleConnectCube(ws, data);
                break;
                
            case 'DISCONNECT_CUBE':
                await this.handleDisconnectCube(ws);
                break;
                
            case 'SEND_COMMAND':
                await this.handleSendCommand(ws, data);
                break;
                
            case 'START_SCANNING':
                await this.handleStartScanning(ws);
                break;
                
            case 'STOP_SCANNING':
                await this.handleStopScanning(ws);
                break;
                
            case 'PING':
                this.sendToClient(ws, { type: 'PONG', timestamp: Date.now() });
                break;
                
            default:
                this.sendToClient(ws, {
                    type: 'ERROR',
                    message: `Unknown message type: ${data.type}`
                });
        }
    }

    /**
     * Handle cube connection request
     */
    async handleConnectCube(ws, data) {
        try {
            if (this.requestConnect) {
                await this.requestConnect(data.address);
            } else {
                this.sendToClient(ws, {
                    type: 'ERROR',
                    message: 'Cube connection handler not available'
                });
            }
        } catch (error) {
            console.error('[Dashboard] Cube connection failed:', error);
            this.sendToClient(ws, {
                type: 'CONNECTION_FAILED',
                message: error.message
            });
        }
    }

    /**
     * Handle cube disconnection request
     */
    async handleDisconnectCube(ws) {
        try {
            if (this.requestDisconnect) {
                await this.requestDisconnect();
            } else {
                this.sendToClient(ws, {
                    type: 'ERROR',
                    message: 'Cube disconnection handler not available'
                });
            }
        } catch (error) {
            console.error('[Dashboard] Cube disconnection failed:', error);
            this.sendToClient(ws, {
                type: 'ERROR',
                message: error.message
            });
        }
    }

    /**
     * Handle send command request
     */
    async handleSendCommand(ws, data) {
        try {
            if (!this.cubeConnection || !this.cubeConnection.getConnectionInfo().isConnected) {
                this.sendToClient(ws, {
                    type: 'ERROR',
                    message: 'No cube connected'
                });
                return;
            }

            await this.cubeConnection.sendCubeCommand(data.command);
            
            this.sendToClient(ws, {
                type: 'COMMAND_SENT',
                command: data.command
            });
            
        } catch (error) {
            console.error('[Dashboard] Command send failed:', error);
            this.sendToClient(ws, {
                type: 'COMMAND_FAILED',
                message: error.message,
                command: data.command
            });
        }
    }

    /**
     * Handle start scanning request
     */
    async handleStartScanning(ws) {
        try {
            if (this.requestScan) {
                this.requestScan();
            } else {
                this.sendToClient(ws, {
                    type: 'ERROR',
                    message: 'Cube scanning handler not available'
                });
            }
        } catch (error) {
            console.error('[Dashboard] Start scanning failed:', error);
            this.sendToClient(ws, {
                type: 'ERROR',
                message: error.message
            });
        }
    }

    /**
     * Handle stop scanning request
     */
    async handleStopScanning(ws) {
        try {
            if (this.requestStopScan) {
                this.requestStopScan();
            } else {
                this.sendToClient(ws, {
                    type: 'ERROR',
                    message: 'Stop scanning handler not available'
                });
            }
        } catch (error) {
            console.error('[Dashboard] Stop scanning failed:', error);
            this.sendToClient(ws, {
                type: 'ERROR',
                message: error.message
            });
        }
    }

    /**
     * Set up cube event handlers to forward events to connected clients
     */
    setupCubeEventHandlers() {
        this.cubeConnection.on('connected', (info) => {
            console.log(`[Dashboard] Cube connected: ${info.deviceName}`);
            this.broadcast({
                type: 'CUBE_CONNECTED',
                cubeInfo: info
            });
        });

        this.cubeConnection.on('disconnected', () => {
            console.log('[Dashboard] Cube disconnected');
            this.broadcast({
                type: 'CUBE_DISCONNECTED'
            });
            this.cubeConnection = null;
        });

        this.cubeConnection.on('cubeFound', (cubeInfo) => {
            console.log(`[Dashboard] Cube found: ${cubeInfo.name}`);
            this.broadcast({
                type: 'CUBE_FOUND',
                cubeInfo: cubeInfo
            });
        });

        this.cubeConnection.on('move', (moveEvent) => {
            this.broadcast({
                type: 'MOVE',
                ...moveEvent
            });
        });

        this.cubeConnection.on('gyro', (gyroEvent) => {
            this.broadcast({
                type: 'GYRO',
                ...gyroEvent
            });
        });

        this.cubeConnection.on('facelets', (faceletsEvent) => {
            this.broadcast({
                type: 'FACELETS',
                ...faceletsEvent
            });
        });

        this.cubeConnection.on('battery', (batteryEvent) => {
            this.broadcast({
                type: 'BATTERY',
                ...batteryEvent
            });
        });

        this.cubeConnection.on('hardware', (hardwareEvent) => {
            this.broadcast({
                type: 'HARDWARE',
                ...hardwareEvent
            });
        });

        this.cubeConnection.on('bluetoothError', (error) => {
            console.error('[Dashboard] Bluetooth error:', error);
            this.broadcast({
                type: 'ERROR',
                message: error.message
            });
        });
    }

    /**
     * Send message to specific client
     */
    sendToClient(ws, message) {
        if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify(message));
        }
    }

    /**
     * Broadcast message to all connected clients
     */
    broadcast(message) {
        const messageStr = JSON.stringify(message);
        
        this.connectedClients.forEach(ws => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(messageStr);
            } else {
                this.connectedClients.delete(ws);
            }
        });
    }

    /**
     * Start the dashboard server
     */
    async start() {
        return new Promise((resolve, reject) => {
            this.httpServer = this.app.listen(this.port, (error) => {
                if (error) {
                    reject(error);
                } else {
                    console.log(`[Dashboard] HTTP server listening on http://localhost:${this.port}`);
                    console.log(`[Dashboard] WebSocket server listening on ws://localhost:${this.wsPort}`);
                    resolve();
                }
            });
        });
    }

    /**
     * Stop the dashboard server
     */
    async stop() {
        // Disconnect cube if connected
        if (this.cubeConnection) {
            await this.cubeConnection.disconnect();
        }

        // Close WebSocket server
        if (this.wss) {
            this.wss.close();
        }

        // Close HTTP server
        if (this.httpServer) {
            return new Promise((resolve) => {
                this.httpServer.close(resolve);
            });
        }
    }

    /**
     * Get server status
     */
    getStatus() {
        return {
            httpPort: this.port,
            wsPort: this.wsPort,
            connectedClients: this.connectedClients.size,
            cubeConnected: this.cubeConnection ? this.cubeConnection.getConnectionInfo().isConnected : false,
            uptime: process.uptime()
        };
    }
}

module.exports = { DashboardServer };