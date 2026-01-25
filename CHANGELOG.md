# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-01-25

### Added
- Institutional-grade CI/CD pipeline with fail-fast gates and semantic release
- Codex audit workflows for code quality verification
- Session state helpers extracted for better testability
- Heartbeat task extraction for cleaner async session logic
- Walkthrough and PR summary documentation

### Changed
- Refactored session module to extract session state helpers
- Moved `logs/` and `state/` directories under `.workspace/` for hermetic isolation
- Improved JSON precedence handling for async sessions

### Fixed
- Circular imports and type errors in session module
- Bitunix client configuration handling

## [1.0.0] - 2026-01-20

### Added
- Initial release of BTC Laptop Agents autonomous trading system
- Paper trading mode with live market data from Bitunix
- Backtest engine with historical data replay
- 7-agent pipeline: MarketIntake, DerivativesFlows, CvdDivergence, SetupSignal, ExecutionRisk, RiskGate, JournalCoach
- Hard safety limits enforced via `constants.py`
- WebSocket reconnection with zombie detection
- Circuit breaker pattern for failure isolation
- SQLite WAL-based broker state persistence
- Rich CLI via Typer (`la` command)
- Pre-commit hooks for code quality
- Comprehensive test suite with pytest

### Security
- pip-audit integration for dependency vulnerability scanning
- Secret scrubbing in logs
- Environment variable isolation via `.env`
