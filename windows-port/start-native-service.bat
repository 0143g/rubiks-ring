@echo off
echo ===============================================
echo GAN Cube Native Windows Controller Service
echo ===============================================
echo.

REM Check if Node.js is installed
node --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js is not installed or not in PATH
    echo.
    echo Please download and install Node.js from:
    echo https://nodejs.org/
    echo.
    pause
    exit /b 1
)

echo Node.js version:
node --version
echo.

REM Check if we're in the right directory
if not exist "package.json" (
    echo ERROR: package.json not found!
    echo Please run this script from the windows-port directory
    echo.
    pause
    exit /b 1
)

echo Installing dependencies...
call npm install
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

echo.
echo Starting GAN Cube Native Service...
echo.
echo Dashboard: http://localhost:3000
echo WebSocket: ws://localhost:8080
echo Input Bridge: ws://localhost:8082
echo.
echo Press Ctrl+C to stop the service
echo.

node src/main.js

echo.
echo Service stopped
pause