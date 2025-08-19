const { GanCubeConnection } = require('./gan-cube-connection');
const { DashboardServer } = require('./dashboard-server');
const { InputBridge } = require('./input-bridge');

/**
 * Main service for native Windows GAN Cube controller system
 */
class GanCubeNativeService {
    constructor() {
        this.cubeConnection = null;
        this.dashboardServer = null;
        this.inputBridge = null;
        this.isRunning = false;
        
        this.setupGracefulShutdown();
    }

    /**
     * Start the native GAN Cube service
     */
    async start() {
        try {
            console.log('🚀 Starting GAN Cube Native Windows Service...');
            console.log('📊 System Information:');
            console.log(`   - Node.js Version: ${process.version}`);
            console.log(`   - Platform: ${process.platform}`);
            console.log(`   - Architecture: ${process.arch}`);
            console.log(`   - PID: ${process.pid}`);
            console.log('');

            // Start dashboard server
            console.log('🌐 Starting Dashboard Server...');
            this.dashboardServer = new DashboardServer();
            await this.dashboardServer.start();
            console.log('✅ Dashboard server started successfully');
            console.log(`   - HTTP: http://localhost:3000`);
            console.log(`   - WebSocket: ws://localhost:8080`);
            console.log('');

            // Start input bridge 
            console.log('🎮 Starting Input Bridge...');
            this.inputBridge = new InputBridge();
            await this.inputBridge.start();
            console.log('✅ Input bridge started successfully');
            console.log(`   - Bridge Port: 8082`);
            console.log('');

            // Initialize cube connection manager (don't connect yet)
            console.log('📡 Initializing Bluetooth System...');
            this.cubeConnection = new GanCubeConnection();
            await this.cubeConnection.initialize();
            console.log('✅ Native Bluetooth initialized');
            console.log('');

            // Set up event forwarding between components
            this.setupEventForwarding();

            this.isRunning = true;
            
            console.log('🎯 GAN Cube Native Service is READY!');
            console.log('');
            console.log('📋 Next Steps:');
            console.log('   1. Open http://localhost:3000 in your browser');
            console.log('   2. Click "Connect Cube" to find and connect your GAN cube');
            console.log('   3. Click "Connect Controller Bridge" to enable gaming input');
            console.log('   4. Start any game and enjoy cube-based gaming!');
            console.log('');
            console.log('🔧 Advanced:');
            console.log('   - For Python bridge: python windows_input_server.py');
            console.log('   - For AutoHotkey bridge: cube-controller.ahk');
            console.log('');
            console.log('Press Ctrl+C to stop the service');

        } catch (error) {
            console.error('❌ Failed to start GAN Cube Native Service:', error.message);
            console.error('Stack trace:', error.stack);
            process.exit(1);
        }
    }

    /**
     * Set up event forwarding between cube connection and other components
     */
    setupEventForwarding() {
        // Forward cube events to dashboard
        this.cubeConnection.on('connected', (info) => {
            console.log(`📱 Cube Connected: ${info.deviceName} (${info.generation})`);
            this.dashboardServer.broadcast({
                type: 'CUBE_CONNECTED',
                cubeInfo: info
            });
            
            this.dashboardServer.cubeConnection = this.cubeConnection;
        });

        this.cubeConnection.on('disconnected', () => {
            console.log('📱 Cube Disconnected');
            this.dashboardServer.broadcast({
                type: 'CUBE_DISCONNECTED'
            });
            
            this.dashboardServer.cubeConnection = null;
        });

        this.cubeConnection.on('cubeFound', (cubeInfo) => {
            console.log(`🔍 Cube Found: ${cubeInfo.name} (${cubeInfo.address})`);
            this.dashboardServer.broadcast({
                type: 'CUBE_FOUND',
                cubeInfo: cubeInfo
            });
        });

        // Forward cube events to input bridge and dashboard
        this.cubeConnection.on('move', (moveEvent) => {
            // Send to input bridge for gaming input
            this.inputBridge.processCubeMove(moveEvent);
            
            // Send to dashboard for visualization
            this.dashboardServer.broadcast({
                type: 'MOVE',
                ...moveEvent
            });
        });

        this.cubeConnection.on('gyro', (gyroEvent) => {
            // Send to input bridge for orientation-based control
            this.inputBridge.processOrientation(gyroEvent);
            
            // Send to dashboard for visualization
            this.dashboardServer.broadcast({
                type: 'GYRO',
                ...gyroEvent
            });
        });

        this.cubeConnection.on('facelets', (faceletsEvent) => {
            this.dashboardServer.broadcast({
                type: 'FACELETS',
                ...faceletsEvent
            });
        });

        this.cubeConnection.on('battery', (batteryEvent) => {
            this.dashboardServer.broadcast({
                type: 'BATTERY',
                ...batteryEvent
            });
        });

        this.cubeConnection.on('hardware', (hardwareEvent) => {
            this.dashboardServer.broadcast({
                type: 'HARDWARE',
                ...hardwareEvent
            });
        });

        this.cubeConnection.on('bluetoothError', (error) => {
            console.error('🔴 Bluetooth Error:', error.message);
            this.dashboardServer.broadcast({
                type: 'ERROR',
                message: `Bluetooth Error: ${error.message}`
            });
        });

        // Set up dashboard server to forward connection requests to cube manager
        this.dashboardServer.cubeConnection = null; // Will be set when cube connects
        this.dashboardServer.requestConnect = async (address) => {
            if (address) {
                await this.cubeConnection.connectToCube(address);
            } else {
                await this.cubeConnection.connectToFirstAvailableCube();
            }
        };

        this.dashboardServer.requestScan = () => {
            this.cubeConnection.startScanning();
            this.dashboardServer.broadcast({
                type: 'SCANNING_STARTED'
            });
        };

        this.dashboardServer.requestStopScan = () => {
            this.cubeConnection.stopScanning();
            this.dashboardServer.broadcast({
                type: 'SCANNING_STOPPED'
            });
        };

        this.dashboardServer.requestDisconnect = async () => {
            if (this.cubeConnection.getConnectionInfo().isConnected) {
                await this.cubeConnection.disconnect();
            }
        };
    }

    /**
     * Stop the service and clean up resources
     */
    async stop() {
        if (!this.isRunning) {
            return;
        }

        console.log('');
        console.log('🛑 Stopping GAN Cube Native Service...');

        try {
            // Disconnect cube
            if (this.cubeConnection && this.cubeConnection.getConnectionInfo().isConnected) {
                console.log('📱 Disconnecting cube...');
                await this.cubeConnection.disconnect();
            }

            // Stop input bridge
            if (this.inputBridge) {
                console.log('🎮 Stopping input bridge...');
                await this.inputBridge.stop();
            }

            // Stop dashboard server
            if (this.dashboardServer) {
                console.log('🌐 Stopping dashboard server...');
                await this.dashboardServer.stop();
            }

            this.isRunning = false;
            console.log('✅ GAN Cube Native Service stopped successfully');

        } catch (error) {
            console.error('❌ Error during service shutdown:', error.message);
        }
    }

    /**
     * Set up graceful shutdown handlers
     */
    setupGracefulShutdown() {
        const shutdown = async (signal) => {
            console.log(`\n🔔 Received ${signal}, shutting down gracefully...`);
            await this.stop();
            process.exit(0);
        };

        process.on('SIGINT', () => shutdown('SIGINT'));
        process.on('SIGTERM', () => shutdown('SIGTERM'));
        process.on('SIGQUIT', () => shutdown('SIGQUIT'));

        // Handle uncaught exceptions
        process.on('uncaughtException', (error) => {
            console.error('🔥 Uncaught Exception:', error.message);
            console.error('Stack trace:', error.stack);
            this.stop().then(() => process.exit(1));
        });

        process.on('unhandledRejection', (reason, promise) => {
            console.error('🔥 Unhandled Rejection at:', promise, 'reason:', reason);
            this.stop().then(() => process.exit(1));
        });
    }

    /**
     * Get service status
     */
    getStatus() {
        return {
            isRunning: this.isRunning,
            cubeConnected: this.cubeConnection ? this.cubeConnection.getConnectionInfo().isConnected : false,
            dashboardRunning: this.dashboardServer !== null,
            inputBridgeRunning: this.inputBridge !== null,
            uptime: process.uptime(),
            memoryUsage: process.memoryUsage(),
            nodeVersion: process.version,
            platform: process.platform
        };
    }
}

// Auto-start service if this file is run directly
if (require.main === module) {
    const service = new GanCubeNativeService();
    
    // Start the service
    service.start().catch(error => {
        console.error('💥 Fatal error starting service:', error);
        process.exit(1);
    });
    
    // Optional: Add CLI-style status reporting
    if (process.argv.includes('--status')) {
        setInterval(() => {
            const status = service.getStatus();
            console.log('📊 Service Status:', JSON.stringify(status, null, 2));
        }, 10000); // Every 10 seconds
    }
}

module.exports = { GanCubeNativeService };