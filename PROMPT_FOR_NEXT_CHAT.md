I am transitioning to a new chat session to implement the "Live Trading System" for my `btc-laptop-agents` project.

**Project Context**:
I have a Python-based trading bot that currently runs reliable **Mock** and **Paper** trading sessions. I now want to transition to **Real Money Live Trading** on Bitunix Futures with small $10 orders.

**Current State**:
- **Codebase**: Existing modular architecture with `orchestrator.py`, `timed_session.py` (polling loop), and `BitunixFuturesProvider`.
- **Broker**: `BitunixBroker` exists in `src/laptop_agents/execution/bitunix_broker.py` and already has some logic for order submission and drift detection.
- **Provider**: `BitunixFuturesProvider` in `src/laptop_agents/data/providers/bitunix_futures.py` has `place_order` and `get_pending_positions` but **MISSING** `cancel_order`.

**The Mission**:
Execute the **4-Phase Live Trading Roadmap** defined in `C:\Users\lovel\.gemini\antigravity\brain\8180824c-9483-4783-bac6-dd4e0356496a\implementation_plan.md`.

**Phase 1: Infrastructure**
- [ ] Implement `cancel_order` in `BitunixFuturesProvider`.
- [ ] Create `scripts/check_live_ready.py` to verify API connectivity and permissions.

**Phase 2: Live Broker**
- [ ] Update `BitunixBroker`:
    - Force **Fixed Size = $10** (ignore strategy qty, use `10.0 / price`).
    - Implement strict precision rounding (`tickSize`, `lotSize` from `fetch_instrument_info`).
    - Add "Human Confirmation" gate for the initial tests (pause for input before submitting).

**Phase 3: Lifecycle**
- [ ] Upgrade "Drift Detection" to **Auto-Correction** (if local != exchange, close/sync).
- [ ] Implement a **Kill Switch** (Ctrl+C or timeout must Cancel All + Close All).

**Key Files to Read First**:
1. `C:\Users\lovel\.gemini\antigravity\brain\8180824c-9483-4783-bac6-dd4e0356496a\implementation_plan.md` (The Roadmap)
2. `C:\Users\lovel\.gemini\antigravity\brain\8180824c-9483-4783-bac6-dd4e0356496a\task.md` (The Checklist)
3. `src/laptop_agents/execution/bitunix_broker.py`
4. `src/laptop_agents/data/providers/bitunix_futures.py`

**Action**:
Start by reading the `implementation_plan.md` and then begin with **Phase 1: Infrastructure**. Let's verify we can cancel an order before we try to place one.
