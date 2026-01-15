"""System preflight checks for deployment readiness."""
import os
import json
from pathlib import Path
from laptop_agents.core.logger import logger

def run_preflight_checks(args) -> bool:
    """Run all preflight checks. Returns True if all pass."""
    checks = []
    
    # 1. Environment variables
    if args.mode in ["live", "live-session"]:
        api_key = os.environ.get("BITUNIX_API_KEY")
        api_secret = os.environ.get("BITUNIX_API_SECRET")
        checks.append(("API_KEY", bool(api_key)))
        checks.append(("API_SECRET", bool(api_secret)))
    else:
        checks.append(("API_KEY (not required)", True))
        checks.append(("API_SECRET (not required)", True))
    
    # 2. Config file
    config_path = Path("config/default.json")
    checks.append(("Config exists", config_path.exists()))
    
    # 3. Logs directory writable
    logs_dir = Path("logs")
    try:
        logs_dir.mkdir(exist_ok=True)
        test_file = logs_dir / ".preflight_test"
        test_file.write_text("test")
        test_file.unlink()
        checks.append(("Logs writable", True))
    except Exception:
        checks.append(("Logs writable", False))
    
    # 4. Network connectivity (Bitunix)
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://fapi.bitunix.com/api/v1/futures/market/tickers?symbols=BTCUSD",
            headers={"User-Agent": "btc-laptop-agents/0.1"}
        )
        urllib.request.urlopen(req, timeout=5)
        checks.append(("Bitunix connectivity", True))
    except Exception:
        checks.append(("Bitunix connectivity", False))
    
    # 5. Python imports
    try:
        from laptop_agents.session.async_session import run_async_session
        from laptop_agents.paper.broker import PaperBroker
        checks.append(("Core imports", True))
    except Exception:
        checks.append(("Core imports", False))
    
    # Report
    all_passed = all(passed for _, passed in checks)
    
    print("\n======== PREFLIGHT CHECK ========")
    for name, passed in checks:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")
    print("=================================")
    print(f"Result: {'READY' if all_passed else 'NOT READY'}\n")
    
    return all_passed
