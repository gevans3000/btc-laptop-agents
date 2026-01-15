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
