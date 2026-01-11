# Git Workflow & Commit Policy

To ensure we can easily rollback and track changes ("Incremental Defense"), we adhere to the following strict Git rules.

## 1. The "Frequency" Rule
**Commit after every logical unit of work.** 
Do not wait for a full feature to be complete. If you fix a bug, commit. If you add a function, commit.
*   **Target**: 1 commit per 15-30 minutes of agent work.
*   **Trigger**: Whenever a test passes or a run succeeds after code changes.

## 2. The "Descriptive" Rule
Use [Conventional Commits](https://www.conventionalcommits.org/) to categorize changes.
*   `fix: ...` for bug fixes.
*   `feat: ...` for new features.
*   `docs: ...` for documentation updates.
*   `chore: ...` for maintenance (styling, logging).
*   `refactor: ...` for code restructuring without behavior change.

## 3. The "Local Authority" Rule
**ALWAYS** use the local `git` CLI (`run_command`) instead of the GitHub API (`push_files`) for code changes.
*   **Why?** We are working in a local workspace. Modifying the remote repo directly creates "split-brain" divergence and merge conflicts.
*   **Exception**: Use GitHub API only for Metadata (Issues, PR comments, Reviews) or when no local repo exists.

## 4. The Checklist (Agent Protocol)
Before every commit, the Agent must:
1.  **Compile Check**: Run `python -m compileall src` to catch syntax errors.
2.  **Add**: `git add .` (Review the status first to ensure no temp files are included).
3.  **Commit**: `git commit -m "type: description"`
4.  **Push**: `git push origin <current_branch>`

## 5. Recovery
If a commit introduces a break, use `git revert <hash>` (safe) or check out the previous commit to inspect.

---
**Agent Command**: To trigger this flow, use the workflow `/save-progress`.
