---
description: Run an audit on the recent code changes and agent health
---

# Audit Buddy Workflow

This workflow allows the AI (Antigravity) to act as an auditor for another agent's work. It checks for "stuck" agents and reviews recent code changes.

## 1. Check Agent Health
First, verify that the running agent is not stuck.
// turbo
python scripts/auditor.py check

## 2. Scan for Artifacts
Check for leftover debug prints or TODOs.
// turbo
python scripts/auditor.py scan

## 3. Review Code Changes
Gather the recent changes (staged, unstaged, and last commit) and analyze them.
// turbo
python scripts/auditor.py diff --commits 1

## 4. Analysis (AI Task)
Read the file `.workspace/audit_diff.txt`.
Analyze the changes for:
1. **Logic Bugs**: Infinite loops, off-by-one errors, incorrect boolean logic.
2. **Safety**: Ensure no sensitive keys are hardcoded.
3. **Performance**: Check for accidental blocking calls in async functions.
4. **Style**: Ensure `logger` is used instead of `print`.

Report your findings to the user.
