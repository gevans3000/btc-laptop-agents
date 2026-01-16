# Scripts Directory

## Active Scripts

| Script | Purpose |
|--------|---------|
| `supervisor.py` | Process watchdog for `la watch` |
| `error_fingerprinter.py` | Error pattern matching for auto-diagnosis |
| `generate_report.py` | Post-run report generation |

## Legacy/Utility Scripts

All other scripts are utilities or one-off tools. Review before using.

## Running Scripts

Most scripts require the repo root in PYTHONPATH:

```powershell
$env:PYTHONPATH = "src"; python scripts/script_name.py
```
