---
description: Capture CLI help and doctor/status outputs for audit evidence
---

# Audit: CLI Output Capture

Goal: capture canonical CLI outputs required by the audit prompt (help + doctor/status).

Steps:
1) Run `la --help` and capture the output verbatim.
2) Run `la doctor` (or `la doctor --fix` if required) and capture output.
3) Run `la status` if available; capture output.
4) If commands fail, capture the error and identify missing dependencies.

Output format:
- Command outputs (verbatim blocks)
- Failures (if any) with error text
- Environment notes (Python version, virtualenv if applicable)

Constraints:
- Read-only: do not modify any files.
- Do not include secrets; scrub environment variables from output.
