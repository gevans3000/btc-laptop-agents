"""
Error Fingerprinter: Capture, hash, and manage error signatures.

Usage:
    python -m laptop_agents.core.diagnostics.fingerprinter capture "<error_message>" "<solution>"
    python -m laptop_agents.core.diagnostics.fingerprinter lookup "<error_message>"
    python -m laptop_agents.core.diagnostics.fingerprinter list
"""

import sys
import json
import hashlib
from datetime import datetime
from typing import Any, Dict, List

from laptop_agents.constants import REPO_ROOT

MEMORY_FILE = REPO_ROOT / ".agent/memory/known_errors.jsonl"


def fingerprint(error_text: str) -> str:
    """Generate a stable hash for an error signature."""
    # Normalize: strip line numbers and timestamps for stable matching
    import re

    normalized = re.sub(r"line \d+", "line N", error_text)
    normalized = re.sub(r"\d{4}-\d{2}-\d{2}", "DATE", normalized)
    normalized = re.sub(r"\d{2}:\d{2}:\d{2}", "TIME", normalized)
    # Remove UUIDs and hex addresses
    normalized = re.sub(r"0x[0-9a-fA-F]+", "0xHEX", normalized)
    normalized = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "UUID",
        normalized,
    )
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def load_memory() -> List[Dict[str, Any]]:
    """Load all known errors from memory."""
    if not MEMORY_FILE.exists():
        return []
    entries: List[Dict[str, Any]] = []
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


def save_all(entries: List[Dict[str, Any]]) -> None:
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


def capture(error_text: str, solution: str, root_cause: str = "") -> None:
    """Capture a new error or update an existing one."""
    if not error_text:
        return

    fp = fingerprint(error_text)
    memory = load_memory()

    updated = False
    for entry in memory:
        if entry.get("fingerprint") == fp:
            # Update occurrence count
            entry["occurrences"] = entry.get("occurrences", 0) + 1
            entry["last_seen"] = datetime.now().isoformat()

            # If the current solution is placeholder and a real one is provided, update it
            if entry.get("solution") in [
                "NEEDS_DIAGNOSIS",
                "Pending Diagnosis",
                "",
            ] and solution not in ["NEEDS_DIAGNOSIS", "Pending Diagnosis"]:
                entry["solution"] = solution
                entry["root_cause"] = root_cause
                print(
                    f"[OK] Updated existing error with new solution (fingerprint: {fp})"
                )
            else:
                print(f"ERROR already known (fingerprint: {fp}), incrementing count.")
            updated = True
            break

    if not updated:
        entry = {
            "fingerprint": fp,
            "error_snippet": error_text[:500],
            "solution": solution,
            "root_cause": root_cause,
            "timestamp": datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat(),
            "occurrences": 1,
        }
        memory.append(entry)
        print(f"[OK] Captured new error (fingerprint: {fp})")

    save_all(memory)


def lookup(error_text: str) -> Dict[str, Any] | None:
    """Lookup an error in memory."""
    fp = fingerprint(error_text)
    memory = load_memory()

    for entry in memory:
        if entry.get("fingerprint") == fp:
            print(f"[OK] MATCH FOUND (fingerprint: {fp})")
            print(f"  First seen: {entry.get('timestamp')}")
            print(f"  Last seen: {entry.get('last_seen', 'N/A')}")
            print(f"  Occurrences: {entry.get('occurrences', 1)}")
            print(f"  Solution: {entry.get('solution')}")
            print(f"  Root cause: {entry.get('root_cause', 'N/A')}")
            return entry

    print(f"No match found for fingerprint: {fp}")
    return None


def list_all() -> None:
    """List all known errors."""
    memory = load_memory()
    print(f"=== Known Errors Database ({len(memory)} entries) ===\n")
    for i, entry in enumerate(memory, 1):
        status = (
            "[OK]"
            if entry.get("solution") not in ["NEEDS_DIAGNOSIS", "Pending Diagnosis", ""]
            else "[WARN]"
        )
        print(
            f"{i}. {status} [{entry.get('fingerprint')}] {entry.get('last_seen', entry.get('timestamp', 'N/A'))}"
        )
        print(f"   Error: {entry.get('error_snippet', '')[:80]}...")
        print(f"   Fix: {entry.get('solution', '')[:80]}...")
        print(f"   Occurrences: {entry.get('occurrences', 1)}")
        print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "capture" and len(sys.argv) >= 4:
        capture(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "")
    elif cmd == "lookup" and len(sys.argv) >= 3:
        lookup(sys.argv[2])
    elif cmd == "list":
        list_all()
    else:
        print(__doc__)
        sys.exit(1)
