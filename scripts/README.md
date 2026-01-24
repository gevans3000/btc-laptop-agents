# Scripts Directory

This directory contains utility scripts for development, testing, and operations.

## Active Scripts

### Development & Testing
- **`testall.ps1`**: Comprehensive test suite runner with stability checks
- **`codex_review.ps1`**: Automated code review using Codex
- **`codex_fix_loop.ps1`**: Automated fix-and-retry loop for test failures
- **`harness.py`**: Test harness for strategy validation

### Diagnostics & Monitoring
- **`check_live_ready.py`**: Verify system readiness for live trading
- **`check_version.py`**: Version consistency checker across project files
- **`check_docs_links.py`**: Validate documentation internal links
- **`check_lint_rules.py`**: Lint rule validation
- **`monitor_heartbeat.py`**: Real-time session heartbeat monitor
- **`diagnose_pending_errors.py`**: Error pattern diagnostics
- **`error_fingerprinter.py`**: Error classification and fingerprinting

### Configuration & Setup
- **`check_bitunix_info.py`**: Fetch and verify Bitunix exchange info
- **`check_symbols.py`**: Symbol validation against exchange
- **`set_safe_temp.ps1`**: Configure safe temp directory for tests
- **`lenovo_local_check.ps1`**: Hardware-specific local environment checks

### Utilities
- **`generate_report.py`**: Session report generator
- **`generate_troubleshooting_docs.py`**: Auto-generate troubleshooting guides
- **`optimize_strategy_v2.py`**: Strategy parameter optimization
- **`verify_autonomy_upgrade.py`**: Autonomy feature verification
- **`verify_safety.py`**: Safety constraint verification
- **`add_regression_test.py`**: Regression test generator
- **`audit_plan.py`**: Audit plan generator
- **`test_everything.py`**: Full system test suite

### Special Files
- **`sitecustomize.py`**: Python startup customization for local dev

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
