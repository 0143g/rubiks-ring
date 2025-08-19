@echo off
echo ===============================================
echo GAN Cube Bluetooth Test
echo ===============================================
echo.

REM Check if Node.js is installed
node --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js is not installed or not in PATH
    echo Please install Node.js first
    pause
    exit /b 1
)

node src/test-bluetooth.js

pause