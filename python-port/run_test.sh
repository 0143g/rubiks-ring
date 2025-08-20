#!/bin/bash

# Run the GAN Smart Cube test script

echo "GAN Smart Cube Connection Test"
echo "==============================="
echo ""

# Check if virtual environment exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Check for dependencies
echo "Checking dependencies..."
python3 -c "import bleak" 2>/dev/null || {
    echo "Installing required dependencies..."
    pip install bleak cryptography numpy
}

# Run the test
echo ""
echo "Starting cube test..."
echo "Make sure your GAN Smart Cube is turned on!"
echo ""

cd "$(dirname "$0")"
python3 test_cube.py