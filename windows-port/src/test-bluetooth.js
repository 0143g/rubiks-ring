const noble = require('@stoprocent/noble');

console.log('🔍 GAN Cube Bluetooth Test');
console.log('==========================');
console.log('');
console.log('Initializing native Bluetooth...');

noble.on('stateChange', (state) => {
    console.log('Bluetooth state:', state);
    
    if (state === 'poweredOn') {
        console.log('✅ Native Bluetooth is working!');
        console.log('✅ Ready to scan for GAN cubes');
        console.log('');
        console.log('Starting 10-second scan for GAN cubes...');
        
        noble.startScanning([], false);
        
        setTimeout(() => {
            noble.stopScanning();
            console.log('');
            console.log('Scan complete!');
            console.log('');
            console.log('If you saw any GAN devices above, your Bluetooth setup is working correctly.');
            console.log('If not, make sure your cube is charged and in pairing mode.');
            process.exit(0);
        }, 10000);
        
    } else {
        console.log('❌ Bluetooth not available or not powered on');
        console.log('');
        console.log('Please check:');
        console.log('- Bluetooth is enabled in Windows Settings');
        console.log('- Bluetooth adapter is working correctly');
        console.log('- No other applications are using Bluetooth exclusively');
        console.log('- Try running as Administrator');
        process.exit(1);
    }
});

noble.on('discover', (peripheral) => {
    const name = peripheral.advertisement.localName;
    if (name && (name.includes('GAN') || name.includes('MoYu') || name.includes('i3'))) {
        console.log('🎲 Found GAN cube:', name, '(' + peripheral.address + ')');
        console.log('   RSSI:', peripheral.rssi + 'dBm');
    } else if (name) {
        // Show other devices but with less emphasis
        console.log('📱 Other device:', name);
    }
});

// Timeout if Bluetooth doesn't initialize
setTimeout(() => {
    if (noble.state !== 'poweredOn') {
        console.log('⏰ Timeout waiting for Bluetooth to initialize');
        console.log('');
        console.log('Troubleshooting:');
        console.log('1. Check Windows Settings → Bluetooth & devices');
        console.log('2. Ensure Bluetooth adapter is enabled');
        console.log('3. Try restarting the Bluetooth service');
        console.log('4. Run as Administrator');
        console.log('5. Close other Bluetooth applications');
        process.exit(1);
    }
}, 5000);

console.log('Waiting for Bluetooth to initialize...');