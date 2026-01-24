---
description: Verify README, pyproject, and CI version/config alignment
---

# Audit: Version & Config Alignment

Goal: detect and report inconsistencies between README, pyproject.toml, and CI workflow requirements.

Steps:
1) Extract stated Python version, config format, and CLI expectations from README.
2) Extract requires-python, dependencies, and CLI entrypoint from pyproject.toml.
3) Extract Python version and checks from .github/workflows/ci.yml.
4) Compare the three sources and list mismatches with file+line references.

Output format:
- Summary (2-4 bullets)
- Mismatches (bullet list with file:line evidence)
- Recommended doc or config alignment actions (no code changes)

Constraints:
- Read-only: do not modify any files.
- Cite file paths and line numbers for all findings.
- If a value is ambiguous, state the ambiguity and what evidence is missing.
