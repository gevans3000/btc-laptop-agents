---
description: Automatically add, commit, and push all changes without asking for confirmation.
---

# Turbo Save Workflow

// turbo-all

This workflow will automatically stage all files, commit them with a generic message, and push to the remote. 
USE WITH CAUTION: This bypasses the usual safety checks and manual commit message writing.

1. Stage all changes
   `git add .`

2. Commit changes
   `git commit -m "wip: auto-save via turbo workflow"`

3. Push to remote
   `git push`
