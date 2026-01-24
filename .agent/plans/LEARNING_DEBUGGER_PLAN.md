# Advanced Learning Debugger Implementation Plan
## Autonomous Execution for Gemini 3 Flash

**Created**: 2026-01-15
**Objective**: Upgrade `/debug` into a Learning Debugger that remembers errors, recalls solutions, and prevents regressions.
**Execution Mode**: Fully autonomous. All non-destructive commands use `SafeToAutoRun: true`.

---

## System Overview

This plan transforms `/debug` from a static check script into an intelligent **Knowledge Loop System** with four capabilities:

| Capability | Component | Purpose |
| :--- | :--- | :--- |
| **Capture** | `scripts/error_fingerprinter.py` | Hash and store errors in memory. |
| **Recall** | `.agent/memory/known_errors.jsonl` | Lookup past solutions before diagnosing. |
| **Test** | `scripts/add_regression_test.py` | Auto-generate tests for fixed bugs. |
| **Prevent** | `.agent/lint_rules.yaml` | Custom lint rules to block bad patterns. |

---

## Phase 1: Create Memory Structure

### 1.1 Create Memory Directory
```powershell
# // turbo
New-Item -ItemType Directory -Path .agent/memory -Force
```

### 1.2 Initialize Known Errors Database
**File**: `.agent/memory/known_errors.jsonl`

Create an empty file with a header comment:
```jsonl
{"_meta": "Known Errors Database", "version": "1.0", "created": "2026-01-15"}
```

### 1.3 Initialize Learned Lint Rules
**File**: `.agent/lint_rules.yaml`

```yaml
# Learned Lint Rules
# These patterns are auto-generated when bugs are fixed.
# They are checked during /pre-commit to prevent regressions.

rules: []
# Example rule structure:
# - id: no-hardcoded-secrets
#   pattern: "API_KEY\\s*=\\s*['\"][^'\"]+['\"]"
#   message: "Do not hardcode API keys. Use environment variables."
#   severity: error
#   source_bug: "2026-01-10: Leaked key in broker.py"
```

### 1.4 Verification
```powershell
# // turbo
Test-Path .agent/memory/known_errors.jsonl
Test-Path .agent/lint_rules.yaml
```

---

## Phase 2: Create Error Fingerprinter Script

### 2.1 Create Script
**File**: `scripts/error_fingerprinter.py`

```python
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
```

### 2.2 Verification
```powershell
# // turbo
python scripts/error_fingerprinter.py list
```

---

## Phase 3: Create Regression Test Generator

### 3.1 Create Script
**File**: `scripts/add_regression_test.py`

```python
"""
Regression Test Generator: Auto-create test cases for fixed bugs.

Usage:
    python scripts/add_regression_test.py "<test_name>" "<description>" "<assertion_code>"

Example:
    python scripts/add_regression_test.py "test_no_hardcoded_size" "Ensure position size is not hardcoded" "assert broker.position_size != 10"
"""
import sys
from pathlib import Path
from datetime import datetime

REGRESSION_DIR = Path("tests/regressions")

TEMPLATE = '''"""
Regression Test: {name}
Generated: {timestamp}
Description: {description}
"""
import pytest

def {name}():
    """
    {description}

    This test was auto-generated after fixing a bug.
    If this test fails, a previously fixed issue has regressed.
    """
    {assertion}
'''

def create_test(name: str, description: str, assertion: str):
    """Create a new regression test file."""
    REGRESSION_DIR.mkdir(parents=True, exist_ok=True)

    # Sanitize name
    safe_name = name.replace(" ", "_").replace("-", "_").lower()
    if not safe_name.startswith("test_"):
        safe_name = f"test_{safe_name}"

    filename = REGRESSION_DIR / f"{safe_name}.py"

    content = TEMPLATE.format(
        name=safe_name,
        timestamp=datetime.now().isoformat(),
        description=description,
        assertion=assertion
    )

    filename.write_text(content, encoding='utf-8')
    print(f"✓ Created regression test: {filename}")
    print(f"  Run with: pytest {filename}")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)

    create_test(sys.argv[1], sys.argv[2], sys.argv[3])
```

### 3.2 Ensure Regression Test Directory Exists
```powershell
# // turbo
New-Item -ItemType Directory -Path tests/regressions -Force
```

### 3.3 Create `__init__.py` for Test Discovery
**File**: `tests/regressions/__init__.py`

```python
"""Regression tests auto-generated from fixed bugs."""
```

### 3.4 Verification
```powershell
# // turbo
python scripts/add_regression_test.py "test_example" "Example regression test" "assert True"
Test-Path tests/regressions/test_example.py
Remove-Item tests/regressions/test_example.py -ErrorAction SilentlyContinue
```

---

## Phase 4: Create Learned Lint Checker

### 4.1 Create Script
**File**: `scripts/check_lint_rules.py`

```python
"""
Learned Lint Checker: Check codebase against learned anti-patterns.

Usage:
    python scripts/check_lint_rules.py
    python scripts/check_lint_rules.py add "<pattern>" "<message>" "<source_bug>"
"""
import sys
import re
import yaml
from pathlib import Path

RULES_FILE = Path(".agent/lint_rules.yaml")
SRC_DIR = Path("src")

def load_rules() -> list:
    """Load lint rules from YAML."""
    if not RULES_FILE.exists():
        return []
    data = yaml.safe_load(RULES_FILE.read_text(encoding='utf-8'))
    return data.get("rules", []) if data else []

def save_rules(rules: list):
    """Save lint rules to YAML."""
    data = {"rules": rules}
    RULES_FILE.write_text(yaml.dump(data, default_flow_style=False), encoding='utf-8')

def check():
    """Run all lint rules against the source code."""
    rules = load_rules()
    if not rules:
        print("No learned lint rules defined.")
        return 0

    violations = []

    for py_file in SRC_DIR.rglob("*.py"):
        content = py_file.read_text(encoding='utf-8')
        lines = content.split('\n')

        for rule in rules:
            pattern = rule.get("pattern")
            if not pattern:
                continue

            for i, line in enumerate(lines, 1):
                if re.search(pattern, line):
                    violations.append({
                        "file": str(py_file),
                        "line": i,
                        "rule_id": rule.get("id", "unknown"),
                        "message": rule.get("message", "Lint violation"),
                        "content": line.strip()[:80]
                    })

    if violations:
        print(f"FAILED: {len(violations)} lint violation(s) found:\n")
        for v in violations:
            print(f"  {v['file']}:{v['line']} [{v['rule_id']}]")
            print(f"    {v['message']}")
            print(f"    > {v['content']}")
            print()
        return 1
    else:
        print("✓ All learned lint rules passed.")
        return 0

def add_rule(pattern: str, message: str, source_bug: str):
    """Add a new lint rule."""
    rules = load_rules()
    rule_id = f"learned-{len(rules) + 1}"

    rules.append({
        "id": rule_id,
        "pattern": pattern,
        "message": message,
        "severity": "error",
        "source_bug": source_bug
    })

    save_rules(rules)
    print(f"✓ Added lint rule: {rule_id}")
    print(f"  Pattern: {pattern}")
    print(f"  Message: {message}")

if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.exit(check())
    elif sys.argv[1] == "add" and len(sys.argv) >= 5:
        add_rule(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        print(__doc__)
        sys.exit(1)
```

### 4.2 Verification
```powershell
# // turbo
python scripts/check_lint_rules.py
```

---

## Phase 5: Create the Learning Debugger Workflow

### 5.1 Create Workflow File
**File**: `.agent/workflows/debug.md` (OVERWRITE existing)

```markdown
---
description: Run systematic checks to diagnose issues
---
# Learning Debugger Workflow

> **Goal**: Diagnose issues, recall past solutions, and prevent future regressions.

## 1. Check Running Processes
// turbo
```powershell
Get-Process python -ErrorAction SilentlyContinue | Format-Table Id, CPU, WS -AutoSize
```

## 2. Check System Readiness
// turbo
```powershell
$env:PYTHONPATH="src"; python scripts/check_live_ready.py
```

## 3. Extract Recent Errors from Logs
// turbo
```powershell
$errors = Get-Content logs/system.jsonl -Tail 200 -ErrorAction SilentlyContinue | Where-Object { $_ -match '"level":\s*"ERROR"' }
if ($errors) {
    Write-Host "⚠ Found $($errors.Count) recent error(s):" -ForegroundColor Yellow
    $errors | Select-Object -Last 3 | ForEach-Object { Write-Host $_ }
} else {
    Write-Host "✓ No recent errors in logs." -ForegroundColor Green
}
```

## 4. Lookup Known Solutions (Memory Recall)
// turbo
If an error was found in Step 3, check if we've seen it before:
```powershell
# Agent should extract error text from Step 3 and run:
# python scripts/error_fingerprinter.py lookup "<error_text>"
python scripts/error_fingerprinter.py list
```

## 5. Run Learned Lint Rules
// turbo
Check if any known bad patterns have re-entered the codebase:
```powershell
python scripts/check_lint_rules.py
```

## 6. Analyze Logs for Patterns
// turbo
```powershell
$latestLog = Get-ChildItem logs/*.log -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($latestLog) { Get-Content $latestLog.FullName -Tail 30 }
```

## 7. Post-Fix Protocol (Manual/Guided)
When you fix a bug, run these commands to capture the learning:

### 7a. Capture the Error in Memory
```powershell
python scripts/error_fingerprinter.py capture "<error_message>" "<solution_description>" "<root_cause>"
```

### 7b. Generate a Regression Test
```powershell
python scripts/add_regression_test.py "<test_name>" "<description>" "<assertion_code>"
```

### 7c. Add a Lint Rule (if applicable)
```powershell
python scripts/check_lint_rules.py add "<regex_pattern>" "<warning_message>" "<bug_reference>"
```

## 8. Clear Cache (Optional)
```powershell
Remove-Item -Recurse -Force __pycache__ -ErrorAction SilentlyContinue
```
```

---

## Phase 6: Update Pre-Commit to Include Lint Rules

### 6.1 Modify Pre-Commit Workflow
If `/pre-commit` workflow exists, add this step after syntax check:

```markdown
## X. Check Learned Lint Rules
// turbo
```powershell
python scripts/check_lint_rules.py
if ($LASTEXITCODE -ne 0) { Write-Host "ABORT: Learned lint rules violated." -ForegroundColor Red; exit 1 }
```
```

---

## Phase 7: Update Documentation

### 7.1 Update `docs/KNOWN_ISSUES.md`
Append the following section:

```markdown
## Auto-Generated Error Log

This section is automatically updated when bugs are captured via the Learning Debugger.

To view all known errors:
```powershell
python scripts/error_fingerprinter.py list
```

To search for a specific error:
```powershell
python scripts/error_fingerprinter.py lookup "<error_text>"
```
```

---

## Phase 8: Final Verification & Commit

### 8.1 Verify All Components
```powershell
# // turbo
@(
    '.agent/memory/known_errors.jsonl',
    '.agent/lint_rules.yaml',
    'scripts/error_fingerprinter.py',
    'scripts/add_regression_test.py',
    'scripts/check_lint_rules.py',
    '.agent/workflows/debug.md',
    'tests/regressions/__init__.py'
) | ForEach-Object {
    if (Test-Path $_) {
        Write-Host "✓ $_" -ForegroundColor Green
    } else {
        Write-Host "✗ MISSING: $_" -ForegroundColor Red
    }
}
```

### 8.2 Run Syntax Check on New Scripts
```powershell
# // turbo
python -m compileall scripts/error_fingerprinter.py scripts/add_regression_test.py scripts/check_lint_rules.py -q
```

### 8.3 Run the New Debug Workflow
```powershell
# // turbo
python scripts/error_fingerprinter.py list
python scripts/check_lint_rules.py
```

### 8.4 Commit All Changes
```powershell
git add .agent/memory/ .agent/lint_rules.yaml .agent/workflows/debug.md scripts/error_fingerprinter.py scripts/add_regression_test.py scripts/check_lint_rules.py tests/regressions/
git commit -m "feat(debug): implement Learning Debugger with memory, regression tests, and lint rules

- Add .agent/memory/known_errors.jsonl for error fingerprinting
- Add scripts/error_fingerprinter.py for capture/lookup
- Add scripts/add_regression_test.py for auto-generating tests
- Add scripts/check_lint_rules.py for learned anti-patterns
- Upgrade /debug workflow to use memory recall
- Create tests/regressions/ directory for regression tests"
git push origin main
```

---

## Self-Correction Protocol

If any verification step fails:
1. Read the error message.
2. Attempt to fix the issue (e.g., missing import, syntax error).
3. Re-run the verification.
4. If the issue persists after 2 attempts, report the blocker and stop.

---

## Usage Examples After Implementation

### Capture a Bug Fix
```powershell
python scripts/error_fingerprinter.py capture "AttributeError: 'NoneType' has no attribute 'price'" "Added null check before accessing price" "API returned null during market close"
```

### Generate a Regression Test
```powershell
python scripts/add_regression_test.py "test_null_price_handling" "Ensure null prices don't crash the system" "from laptop_agents.paper.broker import PaperBroker; broker = PaperBroker(); assert broker.handle_tick({'price': None}) is None"
```

### Add a Lint Rule
```powershell
python scripts/check_lint_rules.py add "position_size\s*=\s*10" "Do not hardcode position size" "2026-01-15: Hardcoded $10 in broker.py"
```

---

**END OF PLAN**
