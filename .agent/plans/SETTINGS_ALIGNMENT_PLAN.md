# Workflow & Skill Alignment Plan
## Autonomous Execution for Gemini 3 Flash

**Created**: 2026-01-15
**Objective**: Synchronize the repository's `.agent` configuration with the latest codebase capabilities.
**Execution Mode**: Fully autonomous. All commands use `SafeToAutoRun: true`.

---

## Phase 1: Cleanup Obsolete Workflows

Delete workflows that have completed their purpose to reduce clutter.

### 1.1 Delete Docs Cleanup Workflows
```powershell
# // turbo
Remove-Item -Force .agent/workflows/docs-cleanup.md -ErrorAction SilentlyContinue
Remove-Item -Force .agent/workflows/docs-cleanup-plan.md -ErrorAction SilentlyContinue
```

---

## Phase 2: Create New Workflows

Create markdown files for the new slash commands.

### 2.1 Create `/optimize` Workflow
**File**: `.agent/workflows/optimize.md`
**Content**:
```markdown
---
description: Run strategy parameter optimization
---
# Strategy Optimization Workflow

> **Goal**: Find best parameters for the current strategy using walk-forward validation.

## 1. Environment Setup
// turbo
```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\Activate.ps1
```

## 2. Run Optimization (V2)
// turbo
```powershell
python scripts/optimize_strategy_v2.py
```

## 3. Verify Output
// turbo
Check if a new configuration was proposed:
```powershell
Get-ChildItem config/strategies/*_optimized.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1
```
```

### 2.2 Create `/monitor` Workflow
**File**: `.agent/workflows/monitor.md`
**Content**:
```markdown
---
description: Launch system monitoring dashboard and logs
---
# System Monitoring Workflow

> **Goal**: Bring up operator visibility tools.

## 1. Check System Status
// turbo
```powershell
.\scripts\mvp_status.ps1
```

## 2. Open Dashboard
// turbo
```powershell
.\scripts\dashboard_up.ps1
```

## 3. Tail Logs
// turbo
```powershell
Get-Content logs/system.jsonl -Tail 20 -Wait
```
```

### 2.3 Rename/Update `/debug` Workflow
**File**: `.agent/workflows/debug.md`
**Content** (Renamed from `workflow-for-debugging.md`):
```markdown
---
description: Run systematic checks to diagnose issues
---
# Debugging Workflow

## 1. Check Processes
// turbo
```powershell
Get-Process python -ErrorAction SilentlyContinue
```

## 2. Check Readiness
// turbo
```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe scripts/check_live_ready.py
```

## 3. Analyze Logs
// turbo
```powershell
$latestLog = Get-ChildItem logs/*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($latestLog) { Get-Content $latestLog.FullName -Tail 50 }
```

## 4. Clear Cache (Optional)
```powershell
Remove-Item -Recurse -Force __pycache__ -ErrorAction SilentlyContinue
```
```

### 2.4 Delete Old Debug Workflow
```powershell
# // turbo
Remove-Item -Force .agent/workflows/workflow-for-debugging.md -ErrorAction SilentlyContinue
```

---

## Phase 3: Verify Skills

Ensure the `monte-carlo` skill is correctly registered (folder existence check).

### 3.1 Verify Monte Carlo Skill
```powershell
# // turbo
python -c "import os; assert os.path.exists('.agent/skills/monte-carlo/SKILL.md'), 'Monte Carlo skill missing'; print('✓ Monte Carlo skill present')"
```

---

## Phase 4: Commit Changes

Save the configuration updates to the repo.

### 4.1 Commit
```powershell
git add .agent/workflows/
git commit -m "chore(config): align agent workflows with codebase capabilities

- Remove obsolete /docs-cleanup workflows
- Add /optimize workflow for strategy tuning
- Add /monitor workflow for ops visibility
- Rename /workflow-for-debugging to /debug
- Validated monte-carlo skill presence"
git push origin main
```

---

## Phase 5: User Notification

Print the final settings block for the user to copy.

```text
Config updated. Please update your Agent Settings with the new block below.
```

---
**END OF PLAN**
