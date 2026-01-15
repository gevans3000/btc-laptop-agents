---
description: Ensure all Markdown documentation and instructions are synchronized with the codebase and each other.
---
# Documentation Synchronization Workflow

> **Goal**: Maintain 100% accuracy in documentation, ensuring no broken links, outdated references, or stale instructions.

## 1. Audit the Core Map
// turbo
Verify that all components and scripts listed in `docs/MAP.md` exist at the specified locations.
```powershell
# Extract paths from MAP.md and check their existence
Select-String -Path docs/MAP.md -Pattern '`src/.*\.py`|`scripts/.*\.ps1`|`scripts/.*\.py`|`config/.*`' | ForEach-Object {
    $path = $_.Matches.Value.Trim('`')
    if (Test-Path $path) {
        Write-Host "✓ Exists: $path" -ForegroundColor Green
    } else {
        Write-Host "✗ MISSING: $path" -ForegroundColor Red
    }
}
```

## 2. Check for Broken Internal Links
// turbo
Scan all documentation for links to internal files that no longer exist.
```powershell
python scripts/check_docs_links.py
```

## 3. Instruction & CLI Alignment
// turbo
Ensure that `docs/RUNBOOK.md` and `docs/SPEC.md` match the current CLI output of `run.py --help`.
```powershell
$env:PYTHONPATH="src"
python src/laptop_agents/run.py --help > temp_help.txt
Write-Host "Current CLI help saved to temp_help.txt. Compare with RUNBOOK.md flags."
```

## 4. Cross-Document Consistency
Review key files for conflicting information:
1.  **MAP.md** vs **SPEC.md** (Architecture vs Implementation)
2.  **RUNBOOK.md** vs **TESTING.md** (Operational steps vs Validation)
3.  **AI_HANDOFF.md** (Ensure it captures the latest state)

## 5. Commit & Debugging Readiness
All documentation changes must follow the **[Commit Workflow](docs/GIT_WORKFLOW.md)**.
- **Atomic Commits**: Keep documentation changes separate from code changes when possible.
- **Descriptive Messages**: Use `docs(scope): message` for all documentation updates.
- **Traceability**: Commits are required to allow for easy rollback and issue tracking.
// turbo
```powershell
git status
Write-Host "Verify all documentation changes are staged and atomic before committing." -ForegroundColor Yellow
```

## 6. Cleanup
// turbo
Remove temporary files.
```powershell
Remove-Item temp_help.txt -ErrorAction SilentlyContinue
```

