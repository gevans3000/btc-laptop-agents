# Now / Next / Later

## Now (Phase D Complete ✓)
- **Modular Architecture Refactor** — COMPLETE
  - ✓ `run.py` reduced to thin CLI wrapper (101 lines)
  - ✓ `orchestrator.py` handles modular/legacy mode dispatch
  - ✓ `loader.py` centralizes candle fetching (mock + bitunix)
  - ✓ `signal.py` implements ATR-based volatility filter (ATR(14)/Close < 0.005 = HOLD)
  - ✓ `exec_engine.py` ends cleanly with no trailing duplicate code

## Next
- **Add more data sources**
  - Done when: Support for Binance and OKX futures data
  - Done when: Unified provider interface for all exchanges

- **Enhance trade simulation**
  - Done when: Multi-bar backtesting with position management
  - Done when: Support for stop-loss and take-profit orders

- **Improve reporting**
  - Done when: Interactive HTML dashboard with charts
  - Done when: Performance metrics and risk analysis

- **Add configuration management**
  - Done when: JSON config files for strategies and parameters
  - Done when: CLI overrides for config values

## Later (Ideas Bucket)
- WebSocket streaming for live data
- Multi-agent collaboration workflows
- Monte Carlo simulation for risk assessment
- Integration with local vector databases
- Automated report generation and email alerts
- Docker container for portable execution
- CI/CD pipeline for automated testing
