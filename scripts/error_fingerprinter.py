"""
Error Fingerprinter: Scans logs, identifies unique error patterns, and updates memory.

Usage:
    python scripts/error_fingerprinter.py list
"""

import sys
import json
import hashlib
import re
from pathlib import Path
from datetime import datetime

# Configuration
PROJECT_ROOT = Path(__file__).parent.parent
LOG_FILE = PROJECT_ROOT / ".workspace/logs/system.jsonl"
MEMORY_FILE = PROJECT_ROOT / ".agent/memory/known_errors.jsonl"
MEMORY_DIR = MEMORY_FILE.parent


def ensure_memory_init():
    """Ensure memory directory and file exist."""
    if not MEMORY_DIR.exists():
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if not MEMORY_FILE.exists():
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            header = {
                "_meta": "Known Errors Database",
                "version": "1.0",
                "updated": datetime.now().isoformat(),
            }
            f.write(json.dumps(header) + "\n")


def get_fingerprint(error_msg: str) -> str:
    """Generate a stable hash for an error message (ignoring dynamic parts)."""
    # Remove dynamic parts like timestamps, IDs, memory addresses
    clean_msg = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", "<TIMESTAMP>", error_msg)
    clean_msg = re.sub(r"0x[0-9a-fA-F]+", "<ADDR>", clean_msg)
    clean_msg = re.sub(
        r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
        "<UUID>",
        clean_msg,
    )
    clean_msg = re.sub(r"\d+", "<NUM>", clean_msg)

    # Hash the cleaned message
    return hashlib.md5(clean_msg.encode("utf-8")).hexdigest()


def capture(
    error_msg: str, solution: str = "NEEDS_DIAGNOSIS", root_cause: str = ""
) -> None:
    """Capture a specific error message directly."""
    ensure_memory_init()
    known = load_known_errors()

    fp = get_fingerprint(error_msg)

    if fp in known:
        known[fp]["occurrences"] = known[fp].get("occurrences", 0) + 1
        known[fp]["last_seen"] = datetime.now().isoformat()
        if (
            solution != "NEEDS_DIAGNOSIS"
            and known[fp].get("solution") == "NEEDS_DIAGNOSIS"
        ):
            known[fp]["solution"] = solution
            known[fp]["root_cause"] = root_cause
    else:
        known[fp] = {
            "fingerprint": fp,
            "error_snippet": error_msg[:200],
            "solution": solution,
            "root_cause": root_cause,
            "occurrences": 1,
            "timestamp": datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat(),
        }

    save_known_errors(known)


def load_known_errors() -> dict:
    """Load known errors into a dict keyed by fingerprint."""
    known = {}
    if not MEMORY_FILE.exists():
        return known

    try:
        content = MEMORY_FILE.read_text(encoding="utf-8").strip()
        for line in content.split("\n"):
            if line and not line.startswith('{"_meta"'):
                try:
                    entry = json.loads(line)
                    known[entry["fingerprint"]] = entry
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return known


def save_known_errors(errors: dict):
    """Save known errors dictionary back to file."""
    header = {
        "_meta": "Known Errors Database",
        "version": "1.0",
        "updated": datetime.now().isoformat(),
    }
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(header) + "\n")
        for start_time in sorted(
            [e.get("timestamp", "") for e in errors.values()], reverse=True
        ):
            # Find entry with this timestamp (inefficient but safe for small DB)
            for entry in errors.values():
                if entry.get("timestamp") == start_time:
                    f.write(json.dumps(entry) + "\n")
                    break


def scan_logs():
    """Scan the log file for errors and return them."""
    if not LOG_FILE.exists():
        print(f"Log file not found: {LOG_FILE}")
        return []

    errors = []
    try:
        # read last 2000 lines efficiently? for now just read all if small, or tail
        # Python doesn't have native tail, reading whole file for now (logs rotate)
        lines = LOG_FILE.read_text(encoding="utf-8").split("\n")
        for line in lines[-1000:]:  # Look at last 1000 lines
            if not line.strip():
                continue
            try:
                log_entry = json.loads(line)
                if log_entry.get("level") == "ERROR":
                    errors.append(log_entry)
            except json.JSONDecodeError:
                continue
    except Exception as e:
        print(f"Error reading logs: {e}")

    return errors


def process_errors(action="list"):
    ensure_memory_init()
    known = load_known_errors()
    recent_errors = scan_logs()

    new_findings = 0
    updated_findings = 0

    for err in recent_errors:
        raw_msg = err.get("event", "") or err.get("message", "Unknown Error")
        fp = get_fingerprint(raw_msg)

        if fp in known:
            known[fp]["occurrences"] = known[fp].get("occurrences", 0) + 1
            known[fp]["last_seen"] = datetime.now().isoformat()
            updated_findings += 1
        else:
            known[fp] = {
                "fingerprint": fp,
                "error_snippet": raw_msg[:200],
                "solution": "NEEDS_DIAGNOSIS",
                "occurrences": 1,
                "timestamp": datetime.now().isoformat(),  # First seen
                "last_seen": datetime.now().isoformat(),
            }
            new_findings += 1

    save_known_errors(known)

    if action == "list":
        print(f"Scanned {len(recent_errors)} recent errors.")
        print(
            f"Found {new_findings} new unique errors, updated {updated_findings} existing."
        )

        # Display solutions if found
        solved = [
            e
            for e in known.values()
            if e.get("solution") and e["solution"] != "NEEDS_DIAGNOSIS"
        ]
        if solved:
            print(f"\n=== KNOWN SOLUTIONS ({len(solved)}) ===")
            for entry in solved:
                print(
                    f"✓ {entry['error_snippet'][:60]}... -> {entry['solution'][:60]}..."
                )
        else:
            print("\nNo known solutions found yet.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        process_errors("list")
    else:
        print(__doc__)
