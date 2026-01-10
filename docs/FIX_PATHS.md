# RESOLVED: Path Resolution for Config Files

> **STATUS**: RESOLVED (Implemented in `run.py` and `cli.py` during Phase 0).

## Issue
When running the application from the `src` directory (as required for Python module resolution), the application was unable to find the `config/default.json` file. This was because it was looking for the file relative to the current working directory (`src/config/default.json`), while the file is actually located in the repository root (`config/default.json`).

## Fix
The `run.py` and `cli.py` have been updated with a robust path resolution mechanism based on `REPO_ROOT` detection.

1. It now automatically detects the **Repository Root** by looking up from its own location.
2. It uses `REPO_ROOT` for all file access (`config`, `.env`, `runs`).
3. This ensures functionality regardless of CWD.

## Prevention
For future development, always use the `REPO_ROOT` variable defined in the entry points.
