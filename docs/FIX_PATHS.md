# Fix: Path Resolution for Config Files

## Issue
When running the application from the `src` directory (as required for Python module resolution), the application was unable to find the `config/default.json` file. This was because it was looking for the file relative to the current working directory (`src/config/default.json`), while the file is actually located in the repository root (`config/default.json`).

## Fix
The `bitunix_cli.py` has been updated with a robust path resolution mechanism:
1. It now automatically detects the **Repository Root** by looking three levels up from its own location.
2. It uses a helper function `resolve_cfg_path()` that:
    - First checks if the path exists relative to the Current Working Directory.
    - If not found, it checks if the path exists relative to the Repository Root.
3. This ensures that commands like `live-session` and `run-history` work correctly whether you run them from the root OR from the `src` folder.
4. It also loads the `.env` file from the Repo Root explicitly to ensure API keys are always found.

## Prevention
For future development, always use the `REPO_ROOT` variable when referencing static assets or configuration files that are not part of the source tree.

Example:
```python
HERE = Path(__file__).resolve()
REPO_ROOT = HERE.parent.parent.parent
# Use REPO_ROOT / "config/default.json"
```
