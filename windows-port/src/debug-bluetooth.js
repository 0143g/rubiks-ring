const noble = require('@stoprocent/noble');

let foundDevices = new Map();
let ganDevicesFound = 0;

console.log('🔍 Enhanced Bluetooth Scanner');
console.log('============================');
console.log('');

noble.on('stateChange', (state) => {
    console.log('Bluetooth state:', state);
    if (state === 'poweredOn') {
        console.log('✅ Bluetooth ready - starting aggressive scan');
        console.log('Scanning for 20 seconds...');
        console.log('');
        
        // Aggressive scanning - all devices, allow duplicates
        noble.startScanning([], true);
        
        setTimeout(() => {
            noble.stopScanning();
            console.log('');
            console.log('📊 SCAN SUMMARY');
            console.log('================');
            console.log('Total unique devices found:', foundDevices.size);
            console.log('GAN-related devices found:', ganDevicesFound);
            console.log('');
            
            if (ganDevicesFound === 0) {
                console.log('❌ No GAN cubes detected');
                console.log('');
                console.log('Troubleshooting:');
                console.log('1. Ensure cube is charged and turned on');
                console.log('2. Try twisting the cube randomly for 5-10 seconds');
                console.log('3. Make sure cube is not connected to another device');
                console.log('4. Try moving closer to the cube');
                console.log('5. Close other Bluetooth applications');
                console.log('6. Try restarting Windows Bluetooth service');
            } else {
                console.log('✅ GAN cube(s) detected! The issue may be with connection, not discovery.');
                console.log('Try using the main service again.');
            }
            
            process.exit(0);
        }, 20000);
    } else {
        console.log('❌ Bluetooth not ready:', state);
        process.exit(1);
    }
});

noble.on('discover', (peripheral) => {
    const addr = peripheral.address;
    const name = peripheral.advertisement.localName || '[unnamed]';
    const rssi = peripheral.rssi;
    const services = peripheral.advertisement.serviceUuids || [];
    
    // Avoid duplicate logging
    const deviceKey = addr + name;
    if (foundDevices.has(deviceKey)) {
        return; // Skip duplicates
    }
    foundDevices.set(deviceKey, true);
    
    // Check if this looks like a GAN cube
    const isGanRelated = name.toLowerCase().includes('gan') || 
                        name.toLowerCase().includes('moyu') || 
                        name.toLowerCase().includes('i3') ||
                        name.includes('356') ||
                        services.some(uuid => 
                            uuid.includes('6e40') || 
                            uuid.includes('8653') || 
                            uuid.includes('fff')
                        );
    
    if (isGanRelated) {
        ganDevicesFound++;
        console.log('🎲 POTENTIAL GAN CUBE:', name);
        console.log('   Address:', addr);
        console.log('   RSSI:', rssi + 'dBm');
        console.log('   Services:', services.length > 0 ? services.join(', ') : 'none advertised');
        console.log('');
    } else {
        console.log('📱', name, '(' + addr + ')', rssi + 'dBm');
    }
});

setTimeout(() => {
    console.log('⏰ Timeout - Bluetooth not initializing');
    process.exit(1);
}, 10000);