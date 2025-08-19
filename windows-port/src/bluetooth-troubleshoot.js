const noble = require('@stoprocent/noble');

console.log('🔧 Windows Bluetooth Connection Troubleshooter');
console.log('==============================================');
console.log('');

console.log('This tool will help diagnose Windows Bluetooth connection issues.');
console.log('');

// Check if we can find the specific cube address that was detected
const TARGET_ADDRESS = 'd4:9d:c0:84:04:d1'; // From the failed connection attempt

let targetPeripheral = null;

noble.on('stateChange', (state) => {
    console.log('Bluetooth state:', state);
    if (state === 'poweredOn') {
        console.log('✅ Bluetooth ready');
        console.log(`🔍 Looking specifically for cube: ${TARGET_ADDRESS}`);
        console.log('');
        noble.startScanning([], true);
    }
});

noble.on('discover', (peripheral) => {
    if (peripheral.address.toLowerCase() === TARGET_ADDRESS.toLowerCase()) {
        if (!targetPeripheral) {
            targetPeripheral = peripheral;
            console.log(`✅ Found target cube: ${peripheral.address}`);
            console.log('   Name:', peripheral.advertisement.localName || '[no name]');
            console.log('   RSSI:', peripheral.rssi + 'dBm');
            console.log('   Services:', peripheral.advertisement.serviceUuids?.join(', ') || '[none]');
            console.log('');
            
            // Try to connect and get detailed error info
            testConnection(peripheral);
        }
    }
});

async function testConnection(peripheral) {
    console.log('🔗 Testing connection...');
    
    try {
        await new Promise((resolve, reject) => {
            const timeout = setTimeout(() => {
                reject(new Error('Connection timeout (15 seconds)'));
            }, 15000);
            
            peripheral.once('connect', () => {
                clearTimeout(timeout);
                console.log('✅ Connection successful!');
                console.log('');
                
                // Try to discover services
                testServiceDiscovery(peripheral).then(resolve).catch(reject);
            });
            
            peripheral.once('disconnect', () => {
                console.log('🔌 Peripheral disconnected');
            });
            
            peripheral.connect((error) => {
                clearTimeout(timeout);
                if (error) {
                    const errorMsg = error?.message || error?.code || error?.toString() || 'Unknown error';
                    console.log('❌ Connection failed:', errorMsg);
                    console.log('   Error type:', typeof error);
                    console.log('   Error object:', error);
                    
                    // Provide specific troubleshooting based on error
                    provideTroubleshooting(error);
                    reject(error);
                } else {
                    console.log('✅ Connect callback successful');
                }
            });
        });
        
    } catch (error) {
        console.log('💥 Connection test failed:', error.message);
        process.exit(1);
    }
}

async function testServiceDiscovery(peripheral) {
    console.log('🔍 Testing service discovery...');
    
    try {
        await new Promise((resolve, reject) => {
            peripheral.discoverServices([], (error, services) => {
                if (error) {
                    console.log('❌ Service discovery failed:', error.message);
                    reject(error);
                } else {
                    console.log(`✅ Found ${services.length} services`);
                    services.forEach(service => {
                        console.log(`   Service: ${service.uuid}`);
                    });
                    
                    if (services.length === 0) {
                        console.log('⚠️ No services found - this might not be a GAN cube');
                    }
                    
                    resolve();
                }
            });
        });
        
        console.log('');
        console.log('🎉 Connection and service discovery successful!');
        console.log('The issue might be with encryption or protocol setup.');
        
    } catch (error) {
        console.log('💥 Service discovery failed:', error.message);
    }
    
    process.exit(0);
}

function provideTroubleshooting(error) {
    console.log('');
    console.log('🛠️ TROUBLESHOOTING:');
    
    const errorString = (error?.message || error?.toString() || '').toLowerCase();
    
    if (errorString.includes('timeout')) {
        console.log('- Cube might be in sleep mode - try twisting it');
        console.log('- Cube might be too far away - move closer');
        console.log('- Windows Bluetooth might be busy - close other BT apps');
    } else if (errorString.includes('access') || errorString.includes('denied')) {
        console.log('- Run as Administrator');
        console.log('- Check Windows Bluetooth permissions');
        console.log('- Disable Windows fast startup');
    } else if (errorString.includes('not found') || errorString.includes('unavailable')) {
        console.log('- Cube might have moved out of range');
        console.log('- Restart Windows Bluetooth service');
        console.log('- Check Device Manager for Bluetooth issues');
    } else {
        console.log('- Try restarting Bluetooth service in Windows');
        console.log('- Try running as Administrator');
        console.log('- Close other Bluetooth applications');
        console.log('- Make sure cube is not paired in Windows Settings');
        console.log('- Try restarting the computer');
    }
    
    console.log('');
}

// Timeout the whole test
setTimeout(() => {
    if (!targetPeripheral) {
        console.log(`❌ Could not find cube ${TARGET_ADDRESS} within 30 seconds`);
        console.log('Make sure the cube is powered on and advertising');
    }
    process.exit(1);
}, 30000);