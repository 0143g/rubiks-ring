@echo off
echo ===============================================
echo GAN Cube Bluetooth Debug Tool
echo ===============================================
echo.

REM Check if Node.js is installed
node --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js is not installed
    pause
    exit /b 1
)

echo Starting enhanced Bluetooth scan...
echo.

node src/debug-bluetooth.js

pause