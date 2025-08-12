#!/usr/bin/env node

const WebSocket = require('ws');

// ANSI color codes for prettier terminal output
const colors = {
    reset: '\x1b[0m',
    bright: '\x1b[1m',
    red: '\x1b[31m',
    green: '\x1b[32m',
    yellow: '\x1b[33m',
    blue: '\x1b[34m',
    magenta: '\x1b[35m',
    cyan: '\x1b[36m',
    white: '\x1b[37m'
};

// Face rotation symbols for visual display
const faceSymbols = {
    'R': '🔴', "R'": '🔴', 'R2': '🔴',
    'L': '🟠', "L'": '🟠', 'L2': '🟠', 
    'U': '⚪', "U'": '⚪', 'U2': '⚪',
    'D': '🟡', "D'": '🟡', 'D2': '🟡',
    'F': '🟢', "F'": '🟢', 'F2': '🟢',
    'B': '🔵', "B'": '🔵', 'B2': '🔵'
};

class CubeReceiver {
    constructor() {
        this.server = null;
        this.moveCount = 0;
        this.lastMoveTime = null;
        this.setupWebSocketServer();
    }

    setupWebSocketServer() {
        console.log(`${colors.cyan}${colors.bright}🎲 GAN Cube Terminal Receiver${colors.reset}`);
        console.log(`${colors.yellow}Starting WebSocket server on ws://localhost:8080${colors.reset}`);
        
        this.server = new WebSocket.Server({ 
            port: 8080,
            host: '0.0.0.0'  // Listen on all interfaces so Windows can connect
        });

        this.server.on('listening', () => {
            console.log(`${colors.green}✅ WebSocket server ready!${colors.reset}`);
            console.log(`${colors.blue}Waiting for browser connection...${colors.reset}`);
            console.log(`${colors.white}Open cube-bridge.html in Chrome and click "Connect to WSL"${colors.reset}\n`);
        });

        this.server.on('connection', (ws, req) => {
            const clientIP = req.socket.remoteAddress;
            console.log(`${colors.green}🔗 Browser connected from ${clientIP}${colors.reset}`);
            
            ws.on('message', (data) => {
                try {
                    const event = JSON.parse(data.toString());
                    this.handleCubeEvent(event);
                } catch (error) {
                    console.log(`${colors.red}❌ Invalid JSON received: ${error.message}${colors.reset}`);
                }
            });

            ws.on('close', () => {
                console.log(`${colors.yellow}🔌 Browser disconnected${colors.reset}`);
            });

            ws.on('error', (error) => {
                console.log(`${colors.red}WebSocket error: ${error.message}${colors.reset}`);
            });
        });

        this.server.on('error', (error) => {
            console.log(`${colors.red}Server error: ${error.message}${colors.reset}`);
        });
    }

    handleCubeEvent(event) {
        const timestamp = new Date().toLocaleTimeString();
        
        if (event.type === 'MOVE') {
            this.moveCount++;
            this.lastMoveTime = Date.now();
            
            const symbol = faceSymbols[event.move] || '❓';
            const moveDisplay = `${colors.bright}${event.move}${colors.reset}`;
            
            // Calculate timing if we have previous move
            let timingInfo = '';
            if (this.lastMoveTime && event.timestamp) {
                const latency = Date.now() - event.timestamp;
                timingInfo = `${colors.white}(${latency}ms latency)${colors.reset}`;
            }
            
            console.log(`${colors.cyan}[${timestamp}]${colors.reset} ${symbol} Move #${this.moveCount}: ${moveDisplay} ${timingInfo}`);
            
            // Show move breakdown if available
            if (event.face !== undefined && event.direction !== undefined) {
                const faceNames = ['U', 'R', 'F', 'D', 'L', 'B'];
                const faceName = faceNames[event.face] || 'Unknown';
                const direction = event.direction === 0 ? 'CW' : 'CCW';
                console.log(`${colors.white}    ↳ Face: ${faceName}, Direction: ${direction}${colors.reset}`);
            }
            
        } else if (event.type === 'FACELETS') {
            console.log(`${colors.magenta}[${timestamp}] 🎲 Cube state updated${colors.reset}`);
            if (event.facelets) {
                console.log(`${colors.white}    ↳ Facelets: ${event.facelets.substring(0, 20)}...${colors.reset}`);
            }
            
        } else {
            console.log(`${colors.yellow}[${timestamp}] 📡 ${event.type}${colors.reset}`);
            console.log(`${colors.white}    ↳ ${JSON.stringify(event)}${colors.reset}`);
        }
    }

    showStats() {
        console.log(`\n${colors.bright}📊 Session Stats:${colors.reset}`);
        console.log(`${colors.white}Total moves detected: ${this.moveCount}${colors.reset}`);
        if (this.lastMoveTime) {
            const elapsed = ((Date.now() - this.lastMoveTime) / 1000).toFixed(1);
            console.log(`${colors.white}Last move: ${elapsed}s ago${colors.reset}`);
        }
    }

    shutdown() {
        console.log(`\n${colors.yellow}🛑 Shutting down...${colors.reset}`);
        this.showStats();
        
        if (this.server) {
            this.server.close(() => {
                console.log(`${colors.green}✅ WebSocket server closed${colors.reset}`);
                process.exit(0);
            });
        } else {
            process.exit(0);
        }
    }
}

// Create and start the receiver
const receiver = new CubeReceiver();

// Graceful shutdown handling
process.on('SIGINT', () => receiver.shutdown());
process.on('SIGTERM', () => receiver.shutdown());

// Show stats every 30 seconds if there's activity
setInterval(() => {
    if (receiver.moveCount > 0) {
        receiver.showStats();
    }
}, 30000);