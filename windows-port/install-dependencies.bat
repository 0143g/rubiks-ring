@echo off
echo ===============================================
echo GAN Cube Native Windows Controller
echo Installing Dependencies
echo ===============================================
echo.

REM Check if Node.js is installed
node --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js is not installed or not in PATH
    echo.
    echo Please download and install Node.js LTS from:
    echo https://nodejs.org/
    echo.
    echo After installing Node.js, restart your computer and run this script again.
    echo.
    pause
    exit /b 1
)

echo Node.js version:
node --version
npm --version
echo.

REM Check if we're in the right directory
if not exist "package.json" (
    echo ERROR: package.json not found!
    echo Please run this script from the windows-port directory
    echo.
    pause
    exit /b 1
)

echo Installing Node.js dependencies...
call npm install
if errorlevel 1 (
    echo.
    echo ERROR: Failed to install Node.js dependencies
    echo.
    echo This might be due to:
    echo - Network connection issues
    echo - Permissions problems
    echo - Missing build tools
    echo.
    echo Try running as Administrator or check your internet connection
    pause
    exit /b 1
)

echo.
echo ===============================================
echo Installation Complete!
echo ===============================================
echo.
echo Next steps:
echo 1. Run 'start-native-service.bat' to start the service
echo 2. Open http://localhost:3000 in your browser
echo 3. Click 'Connect Cube' to find your GAN cube
echo 4. Enjoy native Windows cube gaming!
echo.
echo For gaming input:
echo - Run 'python windows_input_server.py' in another terminal
echo - Or use the existing Python bridge system
echo.
pause