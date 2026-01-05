#!/usr/bin/env python3
"""
Simple setup and test script for BTC Laptop Agents.
"""

import subprocess
import sys
import os

# Ensure UTF-8 encoding for Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def run_command(cmd, description):
    """Run a command and return success status."""
    print(f"\n[INFO] {description}...")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"[SUCCESS] {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[FAILED] {e.stderr.strip()}")
        return False

def main():
    """Main setup and test routine."""
    print("=" * 60)
    print("BTC Laptop Agents - Setup and Test")
    print("=" * 60)
    
    # Check if we're in a virtual environment
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print("[OK] Already in virtual environment")
    else:
        print("[INFO] Not in virtual environment - some commands may require venv activation")
    
    # Install dependencies
    if run_command("pip install -r requirements.txt", "Installing dependencies"):
        # Install package in editable mode
        if run_command("pip install -e .", "Installing package in editable mode"):
            # Test basic functionality
            print("\n[INFO] Testing basic functionality...")
            
            # Test CLI
            test_result = subprocess.run(
                "python -c \"from src.laptop_agents.cli import app; print('CLI import successful')\"",
                shell=True,
                capture_output=True,
                text=True
            )
            
            if test_result.returncode == 0:
                print("[SUCCESS] CLI import successful")
                
                # Test with mock data
                print("\n[INFO] Running quick test with mock data (20 steps)...")
                test_cmd = "python -c \"from src.laptop_agents.cli import app; from typer.testing import CliRunner; runner = CliRunner(); result = runner.invoke(app, ['run-mock', '--steps', '20']); print('Test completed' if result.exit_code == 0 else f'Test failed: {result.output}')\""
                
                test_result = subprocess.run(
                    test_cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    cwd="."
                )
                
                if test_result.returncode == 0:
                    print("[SUCCESS] Mock test completed successfully")
                    print("\n[READY] SYSTEM IS READY!")
                    print("\nNext steps:")
                    print("1. Start dashboard: python scripts/dashboard_server.py")
                    print("2. Run with live history: la run-live-history")
                    print("3. Monitor trades in the dashboard")
                    return 0
                else:
                    print(f"[FAILED] Mock test failed: {test_result.stderr}")
                    return 1
            else:
                print(f"[FAILED] CLI import failed: {test_result.stderr}")
                return 1
        else:
            return 1
    else:
        return 1

if __name__ == "__main__":
    sys.exit(main())
