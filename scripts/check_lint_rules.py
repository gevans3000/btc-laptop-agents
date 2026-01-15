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
                try:
                    if re.search(pattern, line):
                        violations.append({
                            "file": str(py_file),
                            "line": i,
                            "rule_id": rule.get("id", "unknown"),
                            "message": rule.get("message", "Lint violation"),
                            "content": line.strip()[:80]
                        })
                except re.error as e:
                    print(f"Error in regex pattern '{pattern}': {e}")
                    continue
    
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
