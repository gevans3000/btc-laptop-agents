# Scripts Directory

This directory contains utility scripts for development, testing, and operations.

## Active Scripts

### Development & Testing
- **`harness.py`**: Test harness for strategy validation
- **`codex_review.ps1`**: Automated code review using Codex
- **`codex_fix_loop.ps1`**: Automated fix-and-retry loop for test failures
- Note: `testall.ps1` is located at the repository root.

### Diagnostics & Monitoring
- **`check_docs_links.py`**: Validate documentation internal links
- **`check_lint_rules.py`**: Lint rule validation
- **`monitor_heartbeat.py`**: Real-time session heartbeat monitor
- **`diagnose_pending_errors.py`**: Error pattern diagnostics
- **`error_fingerprinter.py`**: Error classification and fingerprinting

### Configuration & Setup
- **`check_symbols.py`**: Symbol validation against exchange
- **`set_safe_temp.ps1`**: Configure safe temp directory for tests

### Utilities
- **`generate_report.py`**: Session report generator
- **`generate_troubleshooting_docs.py`**: Auto-generate troubleshooting guides
- **`optimize_strategy_v2.py`**: Strategy parameter optimization
- **`verify_autonomy_upgrade.py`**: Autonomy feature verification
- **`verify_safety.py`**: Safety constraint verification
- **`add_regression_test.py`**: Regression test generator
- **`audit_plan.py`**: Audit plan generator

### Special Files & Archive
- **`sitecustomize.py`**: Python startup customization for local dev

### 📦 Archived (In `scripts/archive/`)
- **`check_live_ready.py`**: Replaced by `la doctor`
- **`check_version.py`**: Legacy version checker
- **`check_bitunix_info.py`**: Legacy Bitunix info script
- **`lenovo_local_check.ps1`**: Hardware-specific checks
- **`test_everything.py`**: Legacy test runner
- **`audit_plan.py`**: Legacy audit tool

## Usage Patterns

### Run Full Test Suite
```powershell
.\testall.ps1
```

### Quick Lint + Review
```powershell
.\scripts\codex_review.ps1
```

### Verify Live Trading Readiness
```bash
python scripts/check_live_ready.py
```

### Monitor Active Session
```bash
python scripts/monitor_heartbeat.py
```

## Maintenance Notes

- Scripts in `archive/` are deprecated and kept for reference only
- PowerShell scripts are Windows-specific; Python scripts are cross-platform
- All diagnostic scripts should be safe to run in read-only mode
