# Refactor and Consolidate Trading Logic - Implementation Plan

## Goal
Refactor and consolidate the trading agent's codebase to improve maintainability, reduce redundancy, and enhance resilience.

## Progress Tracking
- [x] **1. Consolidate Circuit Breaker Logic**
    - [x] Replace `TradingCircuitBreaker` with `ErrorCircuitBreaker` in `async_session.py` and `timed_session.py`.
    - [x] Update all related method calls (`is_tripped` -> `allow_request`, etc.).
    - [x] Remove `src/laptop_agents/resilience/trading_circuit_breaker.py`. (Pending physical deletion)
- [x] **2. Merge Data Providers**
    - [x] Integrate `BitunixWebsocketClient` and `BitunixWSProvider` into `BitunixFuturesProvider`.
    - [x] Update all imports and calls.
    - [x] Remove `src/laptop_agents/data/providers/bitunix_ws.py`. (Pending physical deletion)
- [x] **3. Centralize Candle Loading**
    - [x] Move `load_mock_candles` and `load_bitunix_candles` to `BitunixFuturesProvider` as static/class methods.
    - [x] Update all references.
    - [x] Remove `src/laptop_agents/data/loader.py`. (Pending physical deletion)
- [x] **4. Consolidate Hard Limits**
    - [x] Move contents of `hard_limits.py` to `constants.py`.
    - [x] Update all import statements.
    - [x] Remove `src/laptop_agents/core/hard_limits.py`. (Pending physical deletion)
- [x] **5. Refactor Signal Generation**
    - [x] Implement `BaseStrategy` and `SMACrossoverStrategy` in `trading/strategy.py`.
    - [x] Replace `generate_signal` calls with the new strategy pattern.
    - [x] Remove `src/laptop_agents/trading/signal.py`. (Pending physical deletion)
- [x] **6. Final Cleanup & Quality Assurance**
    - [x] Physically delete the redundant files.
    - [x] Remove temporary fix scripts (`fix_async.py`, etc.).
    - [x] Run `compileall`, `ruff`, `mypy`, and `pytest`.
    - [x] Fix any remaining flake8/lint issues.
- [x] **7. Commit Progress**
    - [x] Create atomic commits for each logical change.
