@echo off
echo ===============================================
echo GAN Cube Native + Python Gaming Bridge
echo ===============================================
echo.

REM Check if Node.js is installed
node --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js is not installed
    echo Please install Node.js from https://nodejs.org/
    pause
    exit /b 1
)

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed
    echo Please install Python from https://python.org/
    pause
    exit /b 1
)

echo Node.js version:
node --version
echo Python version:
python --version
echo.

REM Install Node.js dependencies if needed
if not exist "node_modules" (
    echo Installing Node.js dependencies...
    call npm install
    if errorlevel 1 (
        echo ERROR: Failed to install Node.js dependencies
        pause
        exit /b 1
    )
)

echo Starting GAN Cube Native Service...
start "GAN Cube Native Service" cmd /k "echo Starting Native Service... && node src/main.js"

REM Wait a moment for the service to start
timeout /t 3 /nobreak >nul

echo Starting Python Gaming Bridge...
start "Python Gaming Bridge" cmd /k "echo Starting Python Bridge... && python ../windows_input_server.py"

echo.
echo ===============================================
echo Both services are starting in separate windows
echo ===============================================
echo.
echo Native Service: http://localhost:3000
echo WebSocket API: ws://localhost:8080  
echo Input Bridge: ws://localhost:8082
echo.
echo Open the dashboard at http://localhost:3000
echo 1. Click 'Connect Cube' to find your GAN cube
echo 2. The Python bridge should auto-connect to port 8082
echo 3. Start gaming!
echo.
echo Close this window when done gaming
echo (The service windows will continue running)
echo.
pause

echo Stopping services...
taskkill /fi "WindowTitle eq GAN Cube Native Service*" /f /t >nul 2>&1
taskkill /fi "WindowTitle eq Python Gaming Bridge*" /f /t >nul 2>&1
echo Services stopped