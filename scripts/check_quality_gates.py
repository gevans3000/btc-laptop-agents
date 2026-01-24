#!/usr/bin/env python3
import os
import sys
import re
from pathlib import Path

# Limits
MAX_LINES = 500
WARN_LINES = 400

# Prohibited patterns
PROHIBITED = [
    (
        r"threading\.Thread",
        "Avoid 'threading.Thread'; use asyncio loops/tasks instead.",
    ),
    (
        r"class .*CircuitBreaker\(",
        "Duplicate CircuitBreaker found. Use 'ErrorCircuitBreaker' from resilience.",
    ),
    (
        r"class .*RateLimiter\(",
        "Duplicate RateLimiter found. Use 'RateLimiter' from core.rate_limiter.",
    ),
    (
        r"open\(.*['\"]w",
        "Avoid direct 'open(..., \"w\")'. Use 'StateManager.atomic_save_json' for state.",
    ),
]

EXEMPT_FILES = [
    "scripts/check_quality_gates.py",  # Self
    "src/laptop_agents/core/state_manager.py",  # Allowed to define atomic writes
    "src/laptop_agents/data/providers/bitunix_futures.py",  # Legacy provider (699 lines)
    "src/laptop_agents/paper/broker.py",  # Legacy broker (1000+ lines)
    "src/laptop_agents/core/orchestrator.py",  # Legacy orchestrator (700+ lines)
    "src/laptop_agents/trading/exec_engine.py",  # Legacy execution engine (660 lines)
]


def check_quality():
    repo_root = Path(__file__).parent.parent
    src_dir = repo_root / "src"

    errors = []

    for root, _, files in os.walk(src_dir):
        for file in files:
            if not file.endswith(".py"):
                continue

            path = Path(root) / file
            rel_path = path.relative_to(repo_root).as_posix()

            if rel_path in EXEMPT_FILES:
                continue

            # File Size Check
            try:
                with open(path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    count = len(lines)
                    content = "".join(lines)

                if count > MAX_LINES:
                    errors.append(f"[SIZE] {rel_path}: {count} lines > {MAX_LINES}")
                elif count > WARN_LINES:
                    print(f"[WARN] {rel_path}: {count} lines (approaching limit)")

                # Pattern Checks
                if rel_path in EXEMPT_FILES:
                    continue

                for pattern, msg in PROHIBITED:
                    if re.search(pattern, content):
                        # Special case exception for StateManager write pattern itself?
                        # Assuming exempt files logic covers it.
                        errors.append(f"[ARCH] {rel_path}: {msg}")

            except Exception as e:
                print(f"[ERR] Could not read {rel_path}: {e}")

    if errors:
        print("\nQuality Gate Failures:")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)
    else:
        print("Quality Gates Passed.")


if __name__ == "__main__":
    check_quality()
