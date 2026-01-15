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
