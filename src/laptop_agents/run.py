from __future__ import annotations
import sys
import subprocess
from pathlib import Path

# run.py - Legacy wrapper for 'la run'
# This file is maintained for backward compatibility. 
# Use 'la run' for all new operations.

HERE = Path(__file__).resolve()
REPO_ROOT = HERE.parent.parent.parent

def main():
    # Pass all arguments to the unified CLI
    cmd = [sys.executable, "-m", "laptop_agents", "run"] + sys.argv[1:]
    # Ensure src is in PYTHONPATH if needed, but 'python -m' usually handles it
    try:
        proc = subprocess.run(cmd)
        sys.exit(proc.returncode)
    except KeyboardInterrupt:
        sys.exit(0)

if __name__ == "__main__":
    main()
