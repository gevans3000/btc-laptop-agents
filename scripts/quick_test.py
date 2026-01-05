#!/usr/bin/env python3
"""
Quick test to check if BTC Laptop Agents is ready to run.
"""

import sys
import os

# Ensure UTF-8 encoding for Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def test_imports():
    """Test if all core modules can be imported."""
    print("Testing core imports...")
    
    try:
        # Test basic Python functionality
        print("[OK] Python is working")
        
        # Test if we can import from src
        sys.path.insert(0, 'src')
        
        # Test core modules
        from laptop_agents.indicators import Candle, ema
        print("[OK] Indicators module imported")
        
        from laptop_agents.agents.state import State
        print("[OK] State module imported")
        
        from laptop_agents.agents.supervisor import Supervisor
        print("[OK] Supervisor module imported")
        
        # Test a simple indicator calculation
        test_candle = Candle(ts="2023-01-01", open=100.0, high=105.0, low=95.0, close=102.0, volume=1000.0)
        test_ema = ema([100.0, 101.0, 102.0, 103.0, 104.0], 3)
        print(f"[OK] EMA calculation works: {test_ema}")
        
        return True
        
    except ImportError as e:
        print(f"[FAILED] Import error: {e}")
        return False
    except Exception as e:
        print(f"[FAILED] Unexpected error: {e}")
        return False

def test_configuration():
    """Test if configuration is valid."""
    print("\nTesting configuration...")
    
    try:
        import json
        from pathlib import Path
        
        config_path = Path("config/default.json")
        if not config_path.exists():
            print("[FAILED] Configuration file not found")
            return False
        
        config = json.loads(config_path.read_text())
        required_keys = ["instrument", "timeframe", "engine", "risk", "derivatives_gates", "setups"]
        
        for key in required_keys:
            if key not in config:
                print(f"[FAILED] Missing configuration key: {key}")
                return False
        
        print("[OK] Configuration is valid")
        return True
        
    except Exception as e:
        print(f"[FAILED] Configuration error: {e}")
        return False

def test_data_structure():
    """Test if data directories exist."""
    print("\nTesting data structure...")
    
    from pathlib import Path
    
    data_dirs = ["data", "logs", "reports"]
    created_dirs = []
    
    for d in data_dirs:
        path = Path(d)
        if not path.exists():
            path.mkdir(exist_ok=True)
            created_dirs.append(d)
    
    if created_dirs:
        print(f"[INFO] Created missing directories: {created_dirs}")
    
    print("[OK] Data structure is ready")
    return True

def main():
    """Run all tests."""
    print("=" * 60)
    print("BTC Laptop Agents - Quick Readiness Test")
    print("=" * 60)
    
    tests = [
        test_imports,
        test_configuration,
        test_data_structure,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"[FAILED] Test failed with exception: {e}")
            results.append(False)
    
    print("\n" + "=" * 60)
    
    if all(results):
        print("✓ SYSTEM IS READY!")
        print("\nYou can now:")
        print("1. Install dependencies: pip install -r requirements.txt")
        print("2. Install package: pip install -e .")
        print("3. Test with mock data: la run-mock --steps 50")
        print("4. Start dashboard: python scripts/dashboard_server.py")
        print("5. Run with live data: la run-live-history")
        return 0
    else:
        print("✗ SYSTEM NOT READY")
        print("\nPlease check the errors above and:")
        print("1. Ensure all dependencies are installed")
        print("2. Check configuration files")
        print("3. Verify Python environment")
        return 1

if __name__ == "__main__":
    sys.exit(main())
