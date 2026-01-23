## Summary
- Updated docs and gitignore to match Python 3.11/JSON configs and ignore generated artifacts.
- Cleaned dependencies (removed `websockets`, added `requirements.lock`) and migrated tooling to Ruff.
- Archived deprecated scripts and removed mutable defaults in config models.
- Replaced argparse-based session CLI with Typer options.
- Consolidated resilience imports, extracted heartbeat and session state helpers.

## Testing
- Not run (per instruction). `pip install -e .` completed with warnings about `packaging`/`streamlit` conflict.

## Notes
- Phase 12 line-count reduction target not met yet (~1605 lines in `async_session.py`).
- Phase 13 deferred (no `bitunix_ws.py` found; aiohttp WebSocket migration pending).
