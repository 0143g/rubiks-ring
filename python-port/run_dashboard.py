#!/usr/bin/env python3
"""
Simple launcher for the GAN Smart Cube Dashboard.
Checks dependencies and starts the web server.
"""

import sys
import subprocess
import importlib

def check_dependencies():
    """Check if required dependencies are installed."""
    required_packages = [
        ('flask', 'Flask'),
        ('flask_socketio', 'Flask-SocketIO'),
        ('socketio', 'python-socketio'),
    ]
    
    missing_packages = []
    
    for package_name, display_name in required_packages:
        try:
            importlib.import_module(package_name)
            print(f"{display_name}")
        except ImportError:
            missing_packages.append(display_name)
            print(f"{display_name} - Missing")
    
    return missing_packages

def install_missing_packages(packages):
    """Install missing packages using pip."""
    if not packages:
        return True
    
    print(f"\nInstalling missing packages: {', '.join(packages)}")
    
    package_map = {
        'Flask': 'flask',
        'Flask-SocketIO': 'flask-socketio', 
        'python-socketio': 'python-socketio'
    }
    
    pip_packages = [package_map.get(pkg, pkg.lower()) for pkg in packages]
    
    try:
        cmd = [sys.executable, '-m', 'pip', 'install'] + pip_packages
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("Installation completed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Installation failed: {e}")
        print(f"Error output: {e.stderr}")
        return False

def main():
    """Main launcher function."""
    print("=" * 40)
    print("Dashboard at: http://localhost:5000")
    
    try:
        # Import and start the dashboard
        from cube_dashboard import CubeDashboardServer
        
        server = CubeDashboardServer()
        server.run(host='0.0.0.0', port=5000, debug=False)
        
    except KeyboardInterrupt:
        print("\n Dashboard stopped by user")
        return 0
    except Exception as e:
        print(f"\nError starting dashboard: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
