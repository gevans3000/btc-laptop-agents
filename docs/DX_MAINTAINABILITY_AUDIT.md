# DX Maintainability Fixes

> **Status:** Ready for Autonomous Execution
> **Agent Mode:** Idempotent / Turbo-All
> **Estimated Time:** 20 minutes

Execute each step sequentially. Skip a step if its idempotency check passes.

---

## Step 1: Rename Test File (Blocker)

**Problem:** `pytest` fails with module collision between `tests/test_trailing_stop.py` and `tests/manual/test_trailing_stop.py`.

**Idempotency Check:**
```powershell
if (Test-Path tests/test_trailing_stop.py) { Write-Host "NEEDED" } else { Write-Host "SKIP" }
```

**Action:**
```powershell
git mv tests/test_trailing_stop.py tests/test_trailing_stop_unit.py
Remove-Item -Recurse -Force tests/__pycache__ -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force tests/manual/__pycache__ -ErrorAction SilentlyContinue
```

**Verify:**
```powershell
pytest tests/ --collect-only 2>&1 | Select-String "error" -NotMatch | Out-Null; if ($?) { Write-Host "OK" } else { Write-Host "FAIL" }
```

---

## Step 2: Add Missing `List` Import (Blocker)

**Problem:** `src/laptop_agents/paper/broker.py` uses `List` type hint (line 56) but doesn't import it.

**Idempotency Check:**
```powershell
if (Select-String -Path src/laptop_agents/paper/broker.py -Pattern "from typing import.*List" -Quiet) { Write-Host "SKIP" } else { Write-Host "NEEDED" }
```

**Action:** Edit `src/laptop_agents/paper/broker.py` line 4:
```python
# Change:
from typing import Any, Dict, Optional, Tuple
# To:
from typing import Any, Dict, List, Optional, Tuple
```

**Verify:**
```powershell
python -c "from laptop_agents.paper.broker import PaperBroker; print('OK')"
```

---

## Step 3: Unify `Candle` Class (Blocker)

**Problem:** Identical `Candle` dataclass defined in both `indicators.py` and `trading/helpers.py`, causing type mismatches.

**Idempotency Check:**
```powershell
$count = (Select-String -Path src/laptop_agents/indicators.py -Pattern "class Candle").Count; if ($count -eq 0) { Write-Host "SKIP" } else { Write-Host "NEEDED" }
```

**Action:** Edit `src/laptop_agents/indicators.py`:
1. Delete lines 8-15 (the `@dataclass class Candle` definition).
2. Add import at top: `from laptop_agents.trading.helpers import Candle`

**Verify:**
```powershell
python -c "from laptop_agents.indicators import Candle; from laptop_agents.trading.helpers import Candle as C2; assert Candle is C2; print('OK')"
```

---

## Step 4: Remove Duplicate `requirements.txt` (Low)

**Problem:** `requirements.txt` duplicates `pyproject.toml` dependencies.

**Idempotency Check:**
```powershell
if (Test-Path requirements.txt) { Write-Host "NEEDED" } else { Write-Host "SKIP" }
```

**Action:**
```powershell
Remove-Item requirements.txt -ErrorAction SilentlyContinue
```

---

## Step 5: Enforce mypy in CI (High)

**Problem:** `.github/workflows/ci.yml` line 19 has `|| true`, suppressing type errors.

**Idempotency Check:**
```powershell
if (Select-String -Path .github/workflows/ci.yml -Pattern "\|\| true" -Quiet) { Write-Host "NEEDED" } else { Write-Host "SKIP" }
```

**Action:** Edit `.github/workflows/ci.yml` line 19:
```yaml
# Change:
      - run: mypy src/laptop_agents --ignore-missing-imports --no-error-summary || true
# To:
      - run: mypy src/laptop_agents --ignore-missing-imports --no-error-summary
```

---

## Step 6: Add Pre-commit Config (Optional)

**Problem:** No automated formatting/linting enforcement.

**Idempotency Check:**
```powershell
if (Test-Path .pre-commit-config.yaml) { Write-Host "SKIP" } else { Write-Host "NEEDED" }
```

**Action:** Create `.pre-commit-config.yaml`:
```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 24.4.2
    hooks:
      - id: black
  - repo: https://github.com/pycqa/flake8
    rev: 7.0.0
    hooks:
      - id: flake8
        args: [--max-line-length=120]
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
```

**Setup:**
```powershell
pip install pre-commit
pre-commit install
```

---

## Final Verification

Run all checks in sequence:

```powershell
# 1. Test collection
pytest tests/ --collect-only

# 2. Smoke test
pytest tests/test_smoke.py -v

# 3. Type check (should have reduced errors)
python -m mypy src/laptop_agents --ignore-missing-imports

# 4. Broker import
python -c "from laptop_agents.paper.broker import PaperBroker"

# 5. Candle unified
python -c "from laptop_agents.indicators import Candle; from laptop_agents.trading.helpers import Candle as C; assert Candle is C"
```

---

## Definition of Done

- [ ] `pytest tests/ --collect-only` succeeds
- [ ] `python -c "from laptop_agents.paper.broker import PaperBroker"` succeeds
- [ ] Single `Candle` class (from `trading.helpers`)
- [ ] No `requirements.txt`
- [ ] CI enforces mypy (no `|| true`)
