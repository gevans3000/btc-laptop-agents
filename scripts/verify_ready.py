#!/usr/bin/env python3
"""
Quick verification script to check if the BTC Laptop Agents system is ready to run.
"""

import sys
import json
import os
from pathlib import Path

# Ensure UTF-8 encoding for Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def check_python_version():
    """Check Python version requirement."""
    major, minor = sys.version_info[:2]
    if major < 3 or (major == 3 and minor < 10):
        return False, f"Python 3.10+ required, found {major}.{minor}"
    return True, f"Python {major}.{minor} ✓"

def check_dependencies():
    """Check if required dependencies are installed."""
    try:
        import typer
        import rich
        import pydantic
        import python_dotenv
        return True, "All dependencies installed ✓"
    except ImportError as e:
        return False, f"Missing dependency: {e}"

def check_configuration():
    """Check if configuration files exist."""
    config_path = Path("config/default.json")
    if not config_path.exists():
        return False, "Missing config/default.json"
    
    try:
        config = json.loads(config_path.read_text())
        required_keys = ["instrument", "timeframe", "engine", "risk", "derivatives_gates", "setups"]
        missing = [k for k in required_keys if k not in config]
        if missing:
            return False, f"Missing config keys: {missing}"
        return True, "Configuration valid ✓"
    except Exception as e:
        return False, f"Invalid configuration: {e}"

def check_data_directories():
    """Check if data directories exist."""
    data_dirs = ["data", "logs", "reports"]
    missing = [d for d in data_dirs if not Path(d).exists()]
    
    if missing:
        # Try to create them
        for d in missing:
            Path(d).mkdir(exist_ok=True)
        return True, f"Created missing directories: {missing} ✓"
    
    return True, "All data directories exist ✓"

def check_agents():
    """Check if agent modules are importable."""
    try:
        from src.laptop_agents.agents import (
            MarketIntakeAgent,
            DerivativesFlowsAgent,
            SetupSignalAgent,
            ExecutionRiskSentinelAgent,
            JournalCoachAgent,
            Supervisor,
            State
        )
        return True, "All agents importable ✓"
    except ImportError as e:
        return False, f"Agent import error: {e}"

def check_providers():
    """Check if data providers are available."""
    try:
        from src.laptop_agents.data.providers import (
            MockProvider,
            BinanceFuturesProvider,
            OkxSwapProvider,
            KrakenSpotProvider,
            BybitDerivativesProvider,
            BitunixFuturesProvider,
            CompositeProvider
        )
        return True, "All providers available ✓"
    except ImportError as e:
        return False, f"Provider import error: {e}"

def main():
    """Run all checks and report status."""
    print("=" * 60)
    print("BTC Laptop Agents - Readiness Check")
    print("=" * 60)
    
    checks = [
        ("Python Version", check_python_version),
        ("Dependencies", check_dependencies),
        ("Configuration", check_configuration),
        ("Data Directories", check_data_directories),
        ("Agents", check_agents),
        ("Providers", check_providers),
    ]
    
    results = []
    for name, check_func in checks:
        try:
            passed, message = check_func()
            results.append((passed, name, message))
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"{status} {name}: {message}")
        except Exception as e:
            results.append((False, name, str(e)))
            print(f"✗ FAIL {name}: {e}")
    
    print("=" * 60)
    
    all_passed = all(result[0] for result in results)
    if all_passed:
        print("✓ SYSTEM READY - You can run the agents!")
        print("\nQuick start commands:")
        print("  1. python -m venv .venv")
        print("  2. .venv\\Scripts\\Activate.ps1 (Windows) or source .venv/bin/activate (Mac/Linux)")
        print("  3. pip install -r requirements.txt")
        print("  4. pip install -e .")
        print("  5. la run_mock --steps 50 (test with mock data)")
        print("  6. python scripts/dashboard_server.py (start dashboard)")
        return 0
    else:
        print("✗ SYSTEM NOT READY - Please fix the issues above")
        return 1

if __name__ == "__main__":
    sys.exit(main())
