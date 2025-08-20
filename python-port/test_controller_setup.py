#!/usr/bin/env python3
"""
Test script to verify the controller bridge setup is working
"""

import sys
import platform
import subprocess
import importlib

def test_platform_support():
    """Test platform-specific libraries"""
    print(f"🖥️ Platform: {platform.system()}")
    
    if platform.system() == "Windows":
        try:
            import win32api
            import win32con
            print("✅ Windows input libraries (pywin32) - OK")
        except ImportError:
            print("❌ Windows input libraries missing - Run: pip install pywin32")
            return False
            
        try:
            import vgamepad
            print("✅ Virtual gamepad library (vgamepad) - OK")
        except ImportError:
            print("⚠️ Virtual gamepad library missing - Will install automatically")
    
    elif platform.system() in ["Linux", "Darwin"]:
        try:
            import pyautogui
            print(f"✅ Cross-platform input library (pyautogui) - OK")
        except ImportError:
            print("❌ pyautogui missing - Run: pip install pyautogui")
            return False
    
    return True

def test_websockets():
    """Test WebSocket library"""
    try:
        import websockets
        print("✅ WebSocket library - OK")
        return True
    except ImportError:
        print("❌ WebSocket library missing - Run: pip install websockets")
        return False

def test_cube_library():
    """Test GAN cube library"""
    try:
        from gan_web_bluetooth import GanSmartCube
        print("✅ GAN cube library - OK")
        return True
    except ImportError as e:
        print(f"❌ GAN cube library missing - {e}")
        return False

def test_dashboard_dependencies():
    """Test dashboard dependencies"""
    try:
        import flask
        import flask_socketio
        print("✅ Dashboard libraries (Flask, SocketIO) - OK")
        return True
    except ImportError:
        print("❌ Dashboard libraries missing - Run: pip install flask flask-socketio")
        return False

def test_controller_config():
    """Test controller configuration file"""
    import os
    import json
    
    config_path = "controller_config.json"
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            print("✅ Controller configuration file - OK")
            print(f"   📋 Found {len(config.get('move_mappings', {}))} move mappings")
            return True
        except Exception as e:
            print(f"❌ Controller configuration file corrupted - {e}")
            return False
    else:
        print("⚠️ Controller configuration file missing (will use defaults)")
        return True

def main():
    """Run all tests"""
    print("🧪 GAN Cube Controller Setup Test")
    print("=" * 40)
    
    tests = [
        ("Platform Support", test_platform_support),
        ("WebSocket Library", test_websockets), 
        ("GAN Cube Library", test_cube_library),
        ("Dashboard Dependencies", test_dashboard_dependencies),
        ("Controller Config", test_controller_config)
    ]
    
    passed = 0
    total = len(tests)
    
    for name, test_func in tests:
        print(f"\n🔍 Testing {name}...")
        try:
            if test_func():
                passed += 1
            else:
                print(f"💥 {name} test failed")
        except Exception as e:
            print(f"💥 {name} test crashed: {e}")
    
    print("\n" + "=" * 40)
    print(f"📊 Test Results: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 All tests passed! Controller setup is ready.")
        print("\n🚀 Next steps:")
        print("1. python run_controller.py")
        print("2. python run_dashboard.py (separate terminal)")
        print("3. Open http://localhost:5000")
        print("4. Connect cube → Enable controller → Play games!")
    else:
        print("⚠️ Some tests failed. Fix the issues above before using controller.")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())