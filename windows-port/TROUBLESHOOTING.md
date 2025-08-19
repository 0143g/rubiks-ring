# GAN Cube Connection Troubleshooting

## Issue: "No GAN cubes found" but Windows sees the cube

If Windows can see your GAN cube in Bluetooth settings but the native service can't find it, follow these steps:

### 🔍 Step 1: Run Debug Tool
```cmd
debug-bluetooth.bat
```
This will show ALL Bluetooth devices and help identify if the cube is being detected.

### 🔋 Step 2: Prepare Your Cube
1. **Charge the cube** - Must be >20% battery
2. **Wake up the cube** - Twist it randomly for 10-15 seconds
3. **Clear connections** - Make sure it's not connected to phone/other device
4. **Stay close** - Keep cube within 3 feet of computer

### 📱 Step 3: Check Windows Bluetooth
1. Open **Settings → Bluetooth & devices**
2. **Remove** the cube if it's already paired
3. **Turn Bluetooth off and on** in Windows
4. Try the native service again

### 🔧 Step 4: Noble/Windows Bluetooth Issues

The @stoprocent/noble library sometimes has issues with Windows Bluetooth drivers:

#### Fix A: Restart Bluetooth Service
1. Press **Win+R**, type `services.msc`
2. Find **"Bluetooth Support Service"**
3. Right-click → **Restart**
4. Try scanning again

#### Fix B: Run as Administrator
1. **Right-click** Command Prompt → **Run as Administrator**  
2. Navigate to windows-port folder
3. Run `start-native-service.bat`

#### Fix C: Check Bluetooth Driver
1. Open **Device Manager**
2. Expand **Bluetooth**
3. Look for any devices with yellow warning icons
4. Update Bluetooth adapter drivers if needed

### 🎯 Step 5: Alternative Connection Methods

If scanning still doesn't work, try connecting by MAC address:

1. In Windows Settings, find your cube's MAC address
2. In the dashboard, use browser console:
   ```javascript
   // Replace with your cube's actual MAC address
   connectToSpecificCube('XX:XX:XX:XX:XX:XX');
   ```

### 📊 Step 6: Check Debug Output

Look at the console output when scanning:
- **"Started scanning for cubes..."** = Scanning started OK
- **"Discovered device: [name]"** = Devices are being found
- **No discover messages** = Bluetooth scanning issue

### 🚨 Known Issues

#### Issue: Windows Bluetooth Stack Conflicts
**Symptoms**: Other Bluetooth apps work, but Noble doesn't find devices
**Solution**: 
1. Close all other Bluetooth applications
2. Disable/enable Bluetooth adapter in Device Manager
3. Restart the native service

#### Issue: Cube Appears as "Unknown Device"
**Symptoms**: Windows sees device but no name/services
**Solution**:
1. Cube battery might be very low
2. Try different GAN cube models (some advertise differently)
3. Use MAC address connection method

#### Issue: Noble Permission Errors
**Symptoms**: "Access denied" or permission errors
**Solution**:
1. Run Command Prompt as Administrator
2. Install Visual Studio Build Tools if not already installed
3. Check Windows UAC settings

### 🔄 Step 7: Try Different Scanning Approaches

The updated code now uses multiple scanning strategies:
1. **Broad scan** - Finds all devices (most reliable)
2. **Service-specific scan** - Looks for GAN service UUIDs
3. **Aggressive mode** - Allows duplicates for better detection
4. **Extended timeout** - 30 seconds instead of 15

### 📝 Reporting Issues

If none of these steps work, please provide:

1. **Debug output** from `debug-bluetooth.bat`
2. **Console output** from the native service
3. **Windows version** and Bluetooth adapter model  
4. **GAN cube model** (GAN356 i3, GAN12 ui, etc.)
5. **Other Bluetooth devices** that work/don't work

### ✅ Success Indicators

You should see these messages when working correctly:
```
[GAN Cube] ✅ Found GAN cube: GAN-i3 (XX:XX:XX:XX:XX:XX) RSSI:-45dBm
[GAN Cube] 🎲 Cube found! Attempting to connect...
[GAN Cube] Connected to GAN-i3
```

### 🎮 Next Steps After Connection

Once connected, test these features:
1. **Dashboard shows cube info** - battery, hardware version
2. **3D visualization updates** when you twist the cube  
3. **Move detection** - R, L, U, D, F, B moves are logged
4. **Orientation data** - quaternion values change when tilting

If connection works but these don't work, that's a different issue (protocol/encryption).