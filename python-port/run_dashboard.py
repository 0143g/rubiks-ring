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
            print(f"✅ {display_name}")
        except ImportError:
            missing_packages.append(display_name)
            print(f"❌ {display_name} - Missing")
    
    return missing_packages

def install_missing_packages(packages):
    """Install missing packages using pip."""
    if not packages:
        return True
    
    print(f"\n📦 Installing missing packages: {', '.join(packages)}")
    
    package_map = {
        'Flask': 'flask',
        'Flask-SocketIO': 'flask-socketio', 
        'python-socketio': 'python-socketio'
    }
    
    pip_packages = [package_map.get(pkg, pkg.lower()) for pkg in packages]
    
    try:
        cmd = [sys.executable, '-m', 'pip', 'install'] + pip_packages
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("✅ Installation completed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Installation failed: {e}")
        print(f"Error output: {e.stderr}")
        return False

def main():
    """Main launcher function."""
    print("🎲 GAN Smart Cube Dashboard Launcher")
    print("=" * 40)
    
    # Check if core library is available
    try:
        import gan_web_bluetooth
        print("✅ gan_web_bluetooth library found")
    except ImportError:
        print("❌ gan_web_bluetooth library not found!")
        print("   Make sure you're running from the python-port directory")
        return 1
    
    print("\n🔍 Checking dashboard dependencies...")
    missing = check_dependencies()
    
    if missing:
        print(f"\n⚠️  Missing {len(missing)} required packages")
        install = input("Install missing packages? (y/N): ").lower().strip()
        
        if install == 'y':
            if not install_missing_packages(missing):
                print("❌ Failed to install dependencies")
                return 1
        else:
            print("❌ Cannot start dashboard without required packages")
            print("   Install manually with: pip install flask flask-socketio python-socketio")
            return 1
    
    print("\n🚀 Starting GAN Smart Cube Dashboard...")
    print("📍 Dashboard will be available at: http://localhost:5000")
    print("🔗 Open that URL in your web browser to access the dashboard")
    print("⏹️  Press Ctrl+C to stop the server\n")
    
    try:
        # Import and start the dashboard
        from cube_dashboard import CubeDashboardServer
        
        server = CubeDashboardServer()
        server.run(host='0.0.0.0', port=5000, debug=False)
        
    except KeyboardInterrupt:
        print("\n⏹️  Dashboard stopped by user")
        return 0
    except Exception as e:
        print(f"\n❌ Error starting dashboard: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())