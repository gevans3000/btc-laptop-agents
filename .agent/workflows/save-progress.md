---
description: Save current progress to GitHub with a standardized commit flow.
---

# Save Progress Workflow

This workflow enforces the "Git Commit Policy" defined in `docs/GIT_WORKFLOW.md`.

## 1. Safety Check
// turbo
Run syntax check to ensure we aren't saving broken code.
`python -m compileall src`

## 2. Status Check
// turbo
Check what is about to be committed.
`git status`

## 3. Commit
**USER ACTION REQUIRED**: 
1. Review the status output above.
2. If correct, run: `git add .`
3. Then run: `git commit -m "type: description"` (Replace type/description with actual values).

## 4. Push
// turbo
`git push`
