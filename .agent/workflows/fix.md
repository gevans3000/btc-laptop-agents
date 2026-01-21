---
description: Minimal, safe auto-fix guidance for Codex
---

# Fix

Goal: fix failing tests with the smallest safe code changes.

Constraints: do not delete files, do not change configs unrelated to the failure, keep edits minimal, preserve repo invariants.

Output format:
1) Summary (1-2 sentences)
2) Changes (bullets with file paths)
3) Tests (commands run or "not run")
4) Risks/Next steps (bullets)
