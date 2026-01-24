---
description: Reconcile walkthrough claims against current repo state
---

# Audit: Walkthrough vs Repo State

Goal: identify mismatches between walkthrough/implementation plan claims and current repo reality.

Steps:
1) Extract key claims from walkthrough.md and IMPLEMENTATION_PLAN.md.
2) Verify each claim against the repo (files/paths/line references).
3) List mismatches and missing artifacts with evidence.

Output format:
- Summary (bullets)
- Verified claims (bulleted list with evidence)
- Mismatches (table: Claim | Evidence | Status)

Constraints:
- Read-only: do not modify any files.
- Cite file paths and line numbers for all findings.
