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
