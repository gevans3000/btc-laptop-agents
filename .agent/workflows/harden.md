---
description: Pre-PR hardening review instructions for Codex
---

# Harden

Goal: identify release-blocking risks and verify readiness for PR.

Constraints: emphasize invariants, config precedence, state persistence, and error paths. Recommend targeted tests or checks.

Output format:
1) Blockers (if none, say "None")
2) High risks (bullets with file:line)
3) Suggested verification steps
