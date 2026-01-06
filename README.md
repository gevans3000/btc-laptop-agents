# BTC Laptop Agents (Local-only)

This repo runs simple agents locally on your laptop. Memory is stored on disk in `src/laptop_agents/data`
and is never synced unless you commit it.

Quick start (PowerShell):
- python -m venv .venv
- .\.venv\Scripts\Activate.ps1
- pip install -r requirements.txt pytest
- pip install -e .
- la run --agent planner "Create a plan for X"
- la tail --n 20

## Sync Pack

Generate a compact sync pack for AI assistants:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\make_sync_pack.ps1
```

Paste the generated `assistant_sync_pack.md` into chat to sync state.
