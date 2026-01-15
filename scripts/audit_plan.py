"""
Audit Plan Verification Script.

Usage: python scripts/audit_plan.py <path_to_plan.md>

Scans a plan markdown file for checkboxes and code references,
then verifies their existence/completion in the codebase.
"""
import sys
import re
from pathlib import Path

def audit_plan(plan_path: str) -> int:
    """Audit a plan file and report completion status."""
    plan = Path(plan_path)
    if not plan.exists():
        print(f"ERROR: Plan file not found: {plan_path}")
        return 1
    
    content = plan.read_text(encoding='utf-8')
    
    # Find all checkbox items
    checkboxes = re.findall(r'- \[([ xX])\] (.+)', content)
    
    # Find all file path references
    file_refs = re.findall(r'`(src/[^`]+\.py|scripts/[^`]+\.py|\.agent/[^`]+\.md)`', content)
    
    print(f"=== Auditing: {plan_path} ===\n")
    
    # Report checkbox status
    completed = sum(1 for c in checkboxes if c[0].lower() == 'x')
    total = len(checkboxes)
    print(f"Checkboxes: {completed}/{total} complete")
    for status, item in checkboxes:
        symbol = "✓" if status.lower() == 'x' else "○"
        print(f"  {symbol} {item[:60]}...")
    
    print()
    
    # Verify file references exist
    missing = []
    for ref in set(file_refs):
        if Path(ref).exists():
            print(f"✓ Exists: {ref}")
        else:
            print(f"✗ MISSING: {ref}")
            missing.append(ref)
    
    print()
    
    # Summary
    if missing:
        print(f"FAILED: {len(missing)} referenced file(s) missing.")
        return 1
    elif total > 0 and completed < total:
        print(f"INCOMPLETE: {total - completed} task(s) remaining.")
        return 0  # Not a failure, just incomplete
    else:
        print("PASSED: All items verified.")
        return 0

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/audit_plan.py <plan.md>")
        sys.exit(1)
    sys.exit(audit_plan(sys.argv[1]))
