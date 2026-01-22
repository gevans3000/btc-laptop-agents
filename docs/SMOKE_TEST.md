# Smoke Test

## Commands
```powershell
.\.venv\Scripts\la.exe doctor --fix
.\.venv\Scripts\python.exe -m laptop_agents run --mode live-session --duration 1 --symbol BTCUSDT --source mock --execution-mode paper --dry-run --async
```
