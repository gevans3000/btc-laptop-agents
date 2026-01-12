---
description: Autonomous merge conflict resolution and repo recovery
---

# Merge Recovery Plan

## Role & Goal
You are an autonomous git repair engine. Execute the following plan to resolve the current broken merge state. Do not ask questions. Make safe assumptions.

## Phase 1: Snapshot & Triage (Run First)

```powershell
# 1. Create safety branch
git checkout -b merge-rescue-$(Get-Date -Format 'yyyyMMdd-HHmmss')

# 2. Capture current state
git status
git diff --name-only --diff-filter=U
git log -3 --oneline
```
**Decision Point**: If `git status` shows "Unmerged paths", proceed to Phase 2. Otherwise, skip to Phase 4.

---

## Phase 2: Conflict Resolution (Apply Heuristics)

### 2.1 Lockfiles (Always Regenerate)
```powershell
# Delete lockfiles with conflicts - they cannot be merged
git checkout --ours package-lock.json 2>$null
git checkout --ours yarn.lock 2>$null
git checkout --ours poetry.lock 2>$null
git checkout --ours pnpm-lock.yaml 2>$null

# Mark as resolved
git add package-lock.json yarn.lock poetry.lock pnpm-lock.yaml 2>$null
```

### 2.2 Generated/Build Directories (Discard)
```powershell
# Remove build artifacts - they will regenerate
git checkout --ours dist/ build/ .next/ __pycache__/ 2>$null
git add dist/ build/ .next/ __pycache__/ 2>$null
```

### 2.3 Config Files (Prefer HEAD, Check for New Keys)
```powershell
# For config conflicts, prefer current branch
git checkout --ours .env.example .eslintrc.js tsconfig.json pyproject.toml 2>$null
git add .env.example .eslintrc.js tsconfig.json pyproject.toml 2>$null
```

### 2.4 Source Code Conflicts (Manual or Theirs)
```powershell
# List remaining unresolved files
$remaining = git diff --name-only --diff-filter=U

if ($remaining) {
    Write-Host "MANUAL RESOLUTION NEEDED for:"
    $remaining
    
    # For simple cases, prefer incoming changes
    foreach ($file in $remaining) {
        git checkout --theirs $file
        git add $file
    }
}
```

---

## Phase 3: Complete the Merge

```powershell
# Verify no remaining conflicts
git diff --name-only --diff-filter=U

# If clean, commit the merge
git commit -m "Merge: resolved conflicts (lockfiles regenerated, config preserved)"
```

---

## Phase 4: Regenerate Dependencies

### For Node.js Projects
```powershell
Remove-Item -Recurse -Force node_modules -ErrorAction SilentlyContinue
npm install
```

### For Python Projects
```powershell
pip install -r requirements.txt
```

---

## Phase 5: Verification Suite

// turbo-all

```powershell
# 1. Lint/Format Check
npm run lint 2>$null; if ($LASTEXITCODE -ne 0) { python -m flake8 src/ 2>$null }

# 2. Type Check
npm run typecheck 2>$null; if ($LASTEXITCODE -ne 0) { python -m mypy src/ 2>$null }

# 3. Build Check
npm run build 2>$null; if ($LASTEXITCODE -ne 0) { python -m build 2>$null }

# 4. Test Suite
$env:PYTHONPATH='src'; python -m pytest -p no:cacheprovider -q
```

---

## Phase 6: Final Status Check

```powershell
# Must show clean working tree
git status

# Confirm on correct branch
git branch --show-current
git log -3 --oneline
```

---

## Definition of Done
- [ ] `git status` shows clean working tree
- [ ] All tests pass
- [ ] Build completes without errors
- [ ] No merge conflict markers (`<<<<<<<`) in any file

## Rollback (If Something Goes Wrong)
```powershell
# Return to the state before this recovery attempt
git merge --abort 2>$null
git reset --hard HEAD~1
git checkout main
git branch -D merge-rescue-*
```
