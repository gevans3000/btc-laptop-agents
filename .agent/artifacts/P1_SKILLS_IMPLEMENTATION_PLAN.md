# P1 Skills Implementation Plan

> **Purpose**: Autonomous implementation of two priority skills for the btc-laptop-agents repository.
> **Target Agent**: Gemini 3 Flash (new session)
> **Execution Mode**: FULLY AUTONOMOUS — No human intervention required.

---

## Objective

Create two skills in `.agent/skills/`:
1. **verify-deploy** — Full system verification loop for deployment readiness
2. **strategy-backtest** — One-shot strategy validation with comparison reporting

---

## Pre-Conditions (Agent MUST Verify)

Before starting, confirm these paths exist:
- [ ] `.venv/` directory exists
- [ ] `config/default.json` exists
- [ ] `scripts/verify.ps1` exists
- [ ] `docs/STRATEGY_CATALOG.md` exists

**Verification Command**:
```powershell
Test-Path .venv, config/default.json, scripts/verify.ps1, docs/STRATEGY_CATALOG.md
```

If any return `False`, STOP and report the missing path.

---

## Task 1: Create `/verify-deploy` Skill

### 1.1 Create Directory Structure
```powershell
New-Item -ItemType Directory -Path ".agent/skills/verify-deploy" -Force
```

### 1.2 Create SKILL.md
**File**: `.agent/skills/verify-deploy/SKILL.md`

**Content**:
```markdown
---
name: verify-deploy
description: Full system verification loop for deployment readiness
---

# Verify & Deploy Skill

This skill runs the complete verification suite to confirm the system is ready for deployment or commit.

## Usage
Invoke with: `/verify-deploy` or "run the verify deploy skill"

## Prerequisites
- Python virtual environment activated
- All dependencies installed

## Steps

// turbo-all

### Step 1: Audit Critical Paths
Verify required files exist:
```powershell
$paths = @('.env', 'config/default.json', '.venv')
$results = @()
foreach ($p in $paths) {
    $exists = Test-Path $p
    $results += [PSCustomObject]@{Path=$p; Exists=$exists}
}
$results | Format-Table -AutoSize
```

### Step 2: Run Unit Tests
```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m pytest tests/ -v --tb=short
```
**Pass Condition**: Exit code 0, no failures.

### Step 3: Smoke Backtest
```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m src.laptop_agents.run --mode backtest --source mock --backtest 100
```
**Pass Condition**: Exit code 0, `runs/latest/summary.html` exists.

### Step 4: Integration Test
```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe scripts/test_dual_mode.py
```
**Pass Condition**: Exit code 0.

### Step 5: Output Summary
After all steps complete, output a summary table:

| Step | Command | Status |
|:---|:---|:---|
| Audit Paths | `Test-Path ...` | PASS/FAIL |
| Unit Tests | `pytest tests/` | PASS/FAIL |
| Smoke Backtest | `--mode backtest` | PASS/FAIL |
| Integration | `test_dual_mode.py` | PASS/FAIL |

## Success Criteria
All 4 steps must PASS for the skill to succeed.

## On Failure
- Do NOT commit any changes
- Report which step failed
- Check `runs/latest/` for artifacts
```

---

## Task 2: Create `/strategy-backtest` Skill

### 2.1 Create Directory Structure
```powershell
New-Item -ItemType Directory -Path ".agent/skills/strategy-backtest" -Force
```

### 2.2 Create SKILL.md
**File**: `.agent/skills/strategy-backtest/SKILL.md`

**Content**:
```markdown
---
name: strategy-backtest
description: Backtest a strategy and compare performance against the baseline
---

# Strategy Backtest Skill

This skill runs a full backtest on any named strategy and compares it against the default baseline.

## Usage
Invoke with: `/strategy-backtest <strategy_name> [bars]`

Examples:
- `/strategy-backtest scalp_1m_sweep`
- `/strategy-backtest scalp_1m_sweep 2000`

## Parameters
- `strategy_name` (required): Name of strategy file in `config/strategies/` (without `.json`)
- `bars` (optional): Number of bars to backtest (default: 1000)

## Steps

// turbo-all

### Step 1: Validate Strategy Exists
```powershell
$strategyPath = "config/strategies/$strategyName.json"
if (-not (Test-Path $strategyPath)) {
    Write-Error "Strategy not found: $strategyPath"
    exit 1
}
Write-Host "Strategy found: $strategyPath"
```

### Step 2: Run Baseline Backtest
Run `default` strategy first to establish baseline:
```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m src.laptop_agents.run --mode backtest --source mock --backtest $bars
```
Save metrics from `runs/latest/stats.json` as baseline.

### Step 3: Run Target Strategy Backtest
```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m src.laptop_agents.run --strategy $strategyName --mode backtest --source mock --backtest $bars
```

### Step 4: Extract Metrics
Parse `runs/latest/stats.json` for:
- `net_pnl`: Net Profit/Loss
- `max_drawdown`: Maximum Drawdown
- `trade_count`: Number of trades
- `win_rate`: Win percentage
- `sharpe_ratio`: Risk-adjusted return (if available)

### Step 5: Generate Comparison Report
Output a comparison table:

| Metric | Baseline (default) | Target ($strategyName) | Delta |
|:---|:---|:---|:---|
| Net PnL | $X | $Y | +/-$Z |
| Max Drawdown | X% | Y% | +/-Z% |
| Trade Count | N | M | +/-K |
| Win Rate | X% | Y% | +/-Z% |

### Step 6: Pass/Fail Determination
The strategy PASSES if:
- Net PnL > 0
- Max Drawdown < 10%
- Trade Count > 10

## Output Artifacts
- Comparison table printed to console
- Full results available in `runs/latest/`

## On Failure
- Report which criteria failed
- Suggest parameter adjustments if drawdown is too high
```

---

## Task 3: Verify Both Skills

After creating both skills, run this verification:

```powershell
# Verify skill files exist
Test-Path ".agent/skills/verify-deploy/SKILL.md"
Test-Path ".agent/skills/strategy-backtest/SKILL.md"

# Validate YAML frontmatter is parseable
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -c "
import yaml
for skill in ['verify-deploy', 'strategy-backtest']:
    with open(f'.agent/skills/{skill}/SKILL.md', 'r') as f:
        content = f.read()
        # Extract frontmatter between --- markers
        parts = content.split('---')
        if len(parts) >= 3:
            yaml.safe_load(parts[1])
            print(f'{skill}: VALID')
        else:
            print(f'{skill}: INVALID FRONTMATTER')
"
```

---

## Task 4: Test the Skills

### Test verify-deploy
```powershell
# Run the full verification loop manually
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m pytest tests/ -v --tb=short
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m src.laptop_agents.run --mode backtest --source mock --backtest 100
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe scripts/test_dual_mode.py
```

### Test strategy-backtest
```powershell
# Backtest the scalp_1m_sweep strategy
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m src.laptop_agents.run --strategy scalp_1m_sweep --mode backtest --source mock --backtest 500
# Check output exists
Test-Path runs/latest/summary.html
```

---

## Task 5: Commit Changes

After all tests pass:

```powershell
git add .agent/skills/
git status
git commit -m "feat(skills): add P1 skills - verify-deploy and strategy-backtest"
git push origin main
```

---

## Success Criteria

| Criterion | Check |
|:---|:---|
| Both SKILL.md files created | `Test-Path` returns True |
| YAML frontmatter valid | Python parse succeeds |
| verify-deploy skill tested | All 4 steps pass |
| strategy-backtest skill tested | Output comparison table generated |
| Changes committed | `git log -1` shows new commit |

---

## Rollback Plan

If anything fails:
```powershell
# Discard uncommitted changes
git checkout -- .agent/skills/

# Or remove newly created directories
Remove-Item -Recurse -Force ".agent/skills/verify-deploy"
Remove-Item -Recurse -Force ".agent/skills/strategy-backtest"
```

---

## Environment Variables

Ensure these are set for all commands:
```powershell
$env:PYTHONPATH = "src"
$env:SKIP_LIVE_CONFIRM = "TRUE"
```

---

## Estimated Time

| Task | Duration |
|:---|:---|
| Pre-condition verification | 30 seconds |
| Create verify-deploy skill | 1 minute |
| Create strategy-backtest skill | 1 minute |
| Test verification | 3 minutes |
| Commit & push | 30 seconds |
| **Total** | ~6 minutes |

---

## Post-Completion Report

After completion, the agent should output:

```
## P1 Skills Implementation: COMPLETE

### Files Created
- .agent/skills/verify-deploy/SKILL.md
- .agent/skills/strategy-backtest/SKILL.md

### Tests Run
| Test | Result |
|:---|:---|
| verify-deploy smoke | PASS |
| strategy-backtest smoke | PASS |

### Git Status
- Commit: feat(skills): add P1 skills - verify-deploy and strategy-backtest
- Pushed: Yes
```

---

*Plan generated: 2026-01-14T15:17:30-05:00*
