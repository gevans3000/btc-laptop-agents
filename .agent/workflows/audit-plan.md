---
description: Verify that all items in a plan file have been completed in the codebase.
---
# Audit Plan Workflow

> **Goal**: Validate that a plan's tasks and file references are fulfilled.

## Prerequisites
- User or agent specifies the plan file path (e.g., `/audit-plan .agent/plans/EXAMPLE.md`).

## 1. Run Audit Script
// turbo
```powershell
# Replace <plan.md> with the actual plan file path
python scripts/audit_plan.py .agent/plans/<plan.md>
```

## 2. Interpret Results
- **PASSED**: All checkboxes marked `[x]` and all file references exist.
- **INCOMPLETE**: Some checkboxes remain unchecked.
- **FAILED**: Referenced files are missing from the codebase.

## 3. Next Steps
If the audit fails or is incomplete, review the plan file and address outstanding items.
