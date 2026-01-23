"""
Diagnose Pending Errors: AI Agent should run this to analyze and solve pending errors.

This script outputs pending errors in a format easy for AI to process and update.

Usage:
    python scripts/diagnose_pending_errors.py list     # Show errors needing diagnosis
    python scripts/diagnose_pending_errors.py solve <fingerprint> "<solution>" "<root_cause>"
"""

import sys
import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
MEMORY_FILE = PROJECT_ROOT / ".agent/memory/known_errors.jsonl"


def load_memory() -> list:
    """Load all known errors from memory."""
    if not MEMORY_FILE.exists():
        return []
    entries = []
    try:
        content = MEMORY_FILE.read_text(encoding="utf-8").strip()
        if not content:
            return []
        for line in content.split("\n"):
            if line and not line.startswith('{"_meta"'):
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except Exception as e:
        print(f"Error loading memory: {e}")
    return entries


def save_all(entries: list):
    """Save all entries back to the memory file."""
    header = {
        "_meta": "Known Errors Database",
        "version": "1.0",
        "updated": datetime.now().isoformat(),
    }
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(header) + "\n")
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def list_pending():
    """List all errors that need diagnosis."""
    memory = load_memory()
    pending = [
        e
        for e in memory
        if e.get("solution") in ["NEEDS_DIAGNOSIS", "Pending Diagnosis", ""]
    ]

    if not pending:
        print("✓ No pending errors. All errors have solutions.")
        return

    print(f"=== PENDING ERRORS ({len(pending)} need diagnosis) ===\n")
    print(
        "AI AGENT: For each error below, analyze the error snippet and provide a solution."
    )
    print(
        'Run: python scripts/diagnose_pending_errors.py solve <fingerprint> "<solution>" "<root_cause>"\n'
    )
    print("-" * 80)

    for entry in pending:
        print(f"FINGERPRINT: {entry.get('fingerprint')}")
        print(f"FIRST SEEN: {entry.get('timestamp')}")
        print(f"OCCURRENCES: {entry.get('occurrences', 1)}")
        print("ERROR SNIPPET:")
        print(f"  {entry.get('error_snippet', 'N/A')}")
        print("-" * 80)


def solve(fingerprint: str, solution: str, root_cause: str = ""):
    """Provide a solution for a pending error."""
    memory = load_memory()
    found = False

    for entry in memory:
        if entry.get("fingerprint") == fingerprint:
            entry["solution"] = solution
            entry["root_cause"] = root_cause
            entry["diagnosed_at"] = datetime.now().isoformat()
            entry["diagnosed_by"] = "AI_AGENT"
            found = True
            break

    if found:
        save_all(memory)
        print(f"✓ Solution recorded for fingerprint: {fingerprint}")
        print(f"  Solution: {solution[:100]}...")
    else:
        print(f"✗ Fingerprint not found: {fingerprint}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "list":
        list_pending()
    elif cmd == "solve" and len(sys.argv) >= 4:
        solve(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "")
    else:
        print(__doc__)
        sys.exit(1)
