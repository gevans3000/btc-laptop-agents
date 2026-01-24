---
description: Verify audit findings include concrete evidence with file/line citations
---

# Audit: Evidence & Citations

Goal: ensure every audit finding contains concrete evidence with file paths and line references.

Steps:
1) Review AUDIT_REPORT_2026.md findings.
2) Confirm each finding includes specific file paths and line-level references or identifiers.
3) Flag findings that only include vague claims (e.g., "appears unused") without citations.

Output format:
- Summary (bullets)
- Findings missing evidence (bulleted list with file:line references to the audit report)
- Recommended evidence sources (list of repo files/commands to gather proof)

Constraints:
- Read-only: do not modify any files.
- Cite file paths and line numbers for all findings.
