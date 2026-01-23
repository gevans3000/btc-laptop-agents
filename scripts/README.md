# Scripts Directory

This directory contains utility scripts for system maintenance, validation, and optimization.

## Core Operational Scripts

| Script | Purpose |
|--------|---------|
| `audit_plan.py` | Verify implementation plans against codebase |
| `diagnose_pending_errors.py` | Analyze and suggest fixes for recent errors |
| `monitor_heartbeat.py` | Watchdog for system health and session status |
| `generate_report.py` | Post-run report generation |
| `generate_troubleshooting_docs.py` | Synchronize error knowledge with documentation |

## Validation & Safety Scripts

| Script | Purpose |
|--------|---------|
| `check_live_ready.py` | Final safety check before live trading |
| `verify_safety.py` | Comprehensive system safety validation |
| `check_bitunix_info.py` | Verify API connectivity and symbol info |
| `verify_autonomy_upgrade.py` | Verify resilience and state recovery logic |
| `check_docs_links.py` | Ensure all documentation links are valid |
| `check_lint_rules.py` | Verify custom linting rules |
| `check_version.py` | Ensure version consistency across the project |
| `check_symbols.py` | Validate trading symbol configuration |

## Optimization & Research

| Script | Purpose |
|--------|---------|
| `optimize_strategy_v2.py` | Hyperparameter optimization for trading strategies |
| `add_regression_test.py` | Helper to create new regression tests from failures |

Deprecated scripts are in `scripts/archive/`.

## Usage

Most scripts require the `src` directory to be in your `PYTHONPATH`:

```powershell
$env:PYTHONPATH = "src"; python scripts/script_name.py
```
