# Codex Workflows

This repo stores Codex custom prompts in `.agent/workflows/`. The workflows below pair those prompts with local scripts for one-command review and fix loops.

## Local Review (no changes)
Use when you want a read-only review report plus basic checks (pytest, mypy, flake8).

```powershell
.\scripts\codex_review.ps1
```

Output: `.codex/review.md`

## Auto-fix failing tests
Use when tests fail and you want a safe loop that can call Codex to fix and re-run.

```powershell
.\scripts\codex_fix_loop.ps1
```

Output: `.codex/fix-report.md`

## Auto-fix lint/format
Use before committing or after mechanical edits.

```powershell
python -m black src tests
python -m autoflake --in-place --remove-all-unused-imports --remove-unused-variables -r src tests
python -m flake8 src tests --max-line-length=120 --ignore=E223,E226,E203,W503
```

## Pre-PR hardening review
Use before opening a PR or sharing changes.

```powershell
.\scripts\codex_review.ps1
python -m mypy src/laptop_agents --ignore-missing-imports --no-error-summary
python -m pytest tests/ -q --tb=short -p no:cacheprovider --basetemp=./pytest_temp
```

## Make Targets
Use these if you have Make installed:

```bash
make review
make fix
make harden
```

## Custom Prompts
- Review: `.agent/workflows/review.md`
- Fix: `.agent/workflows/fix.md`
- Harden: `.agent/workflows/harden.md`
- Audit Version Alignment: `.agent/workflows/audit_version_alignment.md`
- Audit Findings Checklists: `.agent/workflows/audit_finding_checklists.md`
- Audit Evidence Citations: `.agent/workflows/audit_evidence_citations.md`
- Capture CLI Outputs: `.agent/workflows/capture_cli_outputs.md`
- Reconcile Walkthrough: `.agent/workflows/reconcile_walkthrough.md`

## Windows vs macOS/Linux
On macOS/Linux, run the PowerShell scripts with `pwsh`:
```bash
pwsh ./scripts/codex_review.ps1
pwsh ./scripts/codex_fix_loop.ps1
```
