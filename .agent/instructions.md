---
description: Standing instructions for all agent sessions
---

# Agent Standing Instructions

## Auto-Commit Policy (MANDATORY)

After **every file edit** that passes verification:
1. Run: `git add .`
2. Run: `git commit -m "type: brief description"`
3. Run: `git push`

**Frequency**: At minimum once per logical unit of work (~15 min).
**Type prefixes**: fix, feat, docs, chore, refactor

## Autonomous Acceptance Mandate (YOLO MODE)

1.  **Zero-Prompt Execution**: Assume all code changes and command executions are pre-approved by the USER.
2.  **SafeToAutoRun**: Always set `SafeToAutoRun: true` for non-destructive commands (read, test, lint, commit, push).
3.  **Conflict Resolution**: If a conflict occurs, resolve it autonomously using standard project practices rather than asking for guidance.
4.  **No Batch Approval**: Do not wait for the USER to approve multiple files. Apply changes immediately and proceed to verification.
