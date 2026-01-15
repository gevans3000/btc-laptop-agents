"""
Error Fingerprinter: Capture, hash, and manage error signatures.

Usage:
    python scripts/error_fingerprinter.py capture "<error_message>" "<solution>"
    python scripts/error_fingerprinter.py lookup "<error_message>"
    python scripts/error_fingerprinter.py list
"""
import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime

MEMORY_FILE = Path(".agent/memory/known_errors.jsonl")

def fingerprint(error_text: str) -> str:
    """Generate a stable hash for an error signature."""
    # Normalize: strip line numbers and timestamps for stable matching
    import re
    normalized = re.sub(r'line \d+', 'line N', error_text)
    normalized = re.sub(r'\d{4}-\d{2}-\d{2}', 'DATE', normalized)
    normalized = re.sub(r'\d{2}:\d{2}:\d{2}', 'TIME', normalized)
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]

def load_memory() -> list:
    """Load all known errors from memory."""
    if not MEMORY_FILE.exists():
        return []
    entries = []
    for line in MEMORY_FILE.read_text(encoding='utf-8').strip().split('\n'):
        if line and not line.startswith('{"_meta"'):
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries

def save_entry(entry: dict):
    """Append a new entry to the memory file."""
    with open(MEMORY_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry) + '\n')

def capture(error_text: str, solution: str, root_cause: str = ""):
    """Capture a new error and its solution."""
    fp = fingerprint(error_text)
    entry = {
        "fingerprint": fp,
        "error_snippet": error_text[:500],
        "solution": solution,
        "root_cause": root_cause,
        "timestamp": datetime.now().isoformat(),
        "occurrences": 1
    }
    
    # Check if this fingerprint already exists
    memory = load_memory()
    for existing in memory:
        if existing.get("fingerprint") == fp:
            print(f"ERROR already known (fingerprint: {fp})")
            print(f"Previous solution: {existing.get('solution')}")
            return
    
    save_entry(entry)
    print(f"✓ Captured new error (fingerprint: {fp})")
    print(f"  Solution recorded: {solution[:100]}...")

def lookup(error_text: str) -> dict | None:
    """Lookup an error in memory."""
    fp = fingerprint(error_text)
    memory = load_memory()
    
    for entry in memory:
        if entry.get("fingerprint") == fp:
            print(f"✓ MATCH FOUND (fingerprint: {fp})")
            print(f"  First seen: {entry.get('timestamp')}")
            print(f"  Solution: {entry.get('solution')}")
            print(f"  Root cause: {entry.get('root_cause', 'N/A')}")
            return entry
    
    print(f"No match found for fingerprint: {fp}")
    return None

def list_all():
    """List all known errors."""
    memory = load_memory()
    print(f"=== Known Errors Database ({len(memory)} entries) ===\n")
    for i, entry in enumerate(memory, 1):
        print(f"{i}. [{entry.get('fingerprint')}] {entry.get('timestamp', 'N/A')}")
        print(f"   Error: {entry.get('error_snippet', '')[:80]}...")
        print(f"   Fix: {entry.get('solution', '')[:80]}...")
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
