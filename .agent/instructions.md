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

This is NON-NEGOTIABLE. Do not batch multiple edits without commits.
