# Autonomous Trading Improvement Plan

This plan is designed to be executed autonomously by an agent to upgrade the `btc-laptop-agents` system for a reliable, high-fidelity 10-minute paper trading session.

**Rules for Execution:**
1. **Atomic Execution**: Complete one phase fully before moving to the next.
2. **Verification First**: Verify the system is stable after each phase using the provided verification commands.
3. **No User Input**: All steps are self-contained. Resolve any path errors or dependencies autonomously.

---

## Phase 1: Safety & Stability Foundation (Least Risk)
**Goal**: Prevent crashes from logging, state corruption, or memory leaks.

### 1.1 Secure & Safe Logging
**Task**: Update `src/laptop_agents/core/logger.py`.
- **Action**: Implement a `SensitiveDataFilter(logging.Filter)` class.
- **Logic**: Use Regex to catch and replace Bitunix API keys (e.g., `[a-zA-Z0-9]{32,}`) with `***` in log records.
- **Action**: Attach this filter to all file and console handlers in `setup_logger`.
- **Verification**: Run `python -c "from laptop_agents.core.logger import logger; logger.info('API Key: 12345678901234567890123456789012')"`. Check `logs/system.jsonl` to ensure it is redacted.

### 1.2 Corrupt State Recovery
**Task**: Update `src/laptop_agents/paper/broker.py`.
- **Action**: In `_load_state()`, wrap the `json.load(f)` call in a broad `try/except`.
- **Logic**: If loading fails (JSONDecodeError), rename the corrupt file to `state.json.corrupt`, log a Critical warning, and initialize with default state. Do NOT crash.
- **Verification**: Create a corrupt `paper/async_broker_state.json` with content `{broken...`. Run a short session `python src/laptop_agents/run.py --mode live-session --duration 1`. It should start without error.

### 1.3 Unbounded Queue Protection
**Task**: Update `src/laptop_agents/data/providers/bitunix_ws.py`.
- **Action**: In `__init__`, set `self.queue = asyncio.Queue(maxsize=1000)`.
- **Action**: In `_handle_messages`, change `await self.queue.put(tick)` to:
  ```python
  try:
      self.queue.put_nowait(tick)
  except asyncio.QueueFull:
      # Optional: log efficient warning (don't spam)
      pass
  ```
- **Verification**: Manual code review is sufficient (behavioral test is hard without load).

---

## Phase 2: High-Fidelity Execution Logic
**Goal**: Make paper trading behavior match real-world partial fills, spreads, and latency.

### 2.1 Latency Realism (Look-Ahead Bias Fix)
**Task**: Update `src/laptop_agents/session/async_session.py`.
- **Action**: In `on_candle_closed`, modify the execution flow:
  1. Calculate `signal` and `order` based on `candle.close`.
  2. `await asyncio.sleep(self.execution_latency_ms / 1000.0)`
  3. **CRITICAL**: After waking up, grab `current_tick = self.latest_tick`.
  4. Pass `current_tick` (not the candle!) to `self.broker.on_candle(..., tick=current_tick)`.
- **Reason**: This forces the broker to use the *future* price after the latency delay, simulating real slippage vs the signal price.

### 2.2 Bid/Ask Spread Simulation
**Task**: Update `src/laptop_agents/paper/broker.py`.
- **Action**: In `_try_fill`, refine the "market" order fill logic:
  ```python
  if tick and tick.bid and tick.ask:
      # BUY fills at ASK, SELL fills at BID
      fill_px = float(tick.ask) if side == "LONG" else float(tick.bid)
      actual_slip_bps = 0.0 # Spread essentially IS the slippage
  else:
      fill_px = float(candle.close)
      actual_slip_bps = self.slip_bps # Fallback
  ```
- **Verification**: Run a session with `--execution-latency-ms 1000`. Check logs. You should see "Strategy Fill" prices differing slightly from "Candle Close" prices due to the 1s delay and spread.

### 2.3 Active Circuit Breaker Gating
**Task**: Update `src/laptop_agents/session/async_session.py`.
- **Action**: In `on_candle_closed`, *before* calculating signals:
  ```python
  if self.circuit_breaker.is_tripped():
      logger.warning("SIGNAL BLOCKED: Circuit breaker is tripped.")
      return
  ```
- **Reason**: Prevents "ghost signals" from being processed or logged when the system should be dead.

---

## Phase 3: Network Reliability
**Goal**: Survive connection drops and platform instability.

### 3.1 WS Resiliency & Re-subscription
**Task**: Update `src/laptop_agents/data/providers/bitunix_ws.py`.
- **Action**: Add a `self.subscriptions = set()` to track active channels.
- **Action**: Update `subscribe_kline` and `subscribe_ticker` to add to this set.
- **Action**: Create a `_resubscribe()` method that iterates `self.subscriptions` and sends the subscribe messages again.
- **Action**: Call `await self._resubscribe()` strictly *after* `await websockets.connect(self.URL)` inside the `listen` loop (before the inner while loop).
- **Verification**: Disconnect internet during a run (if possible) or modify code to raise `ConnectionClosed` once. Ensure logs show "Resubscribing to..." after reconnect.

---

## Phase 4: Autonomy & Observability
**Goal**: Run without humans, report results clearly.

### 4.1 Structured Run Reports
**Task**: Update `src/laptop_agents/session/async_session.py`.
- **Action**: In the `finally` block of `run()`, write `LATEST_DIR / "final_report.json"`.
- **Content**:
  ```json
  {
      "status": "success/error",
      "exit_code": 0/1,
      "pnl_absolute": -50.2,
      "error_count": 0,
      "duration_seconds": 600
  }
  ```
- **Reason**: Allows wrapper scripts to know exactly what happened without parsing HTML.

### 4.2 The Supervisor Loop
**Task**: Create `scripts/run_autonomous_loop.ps1`.
- **Content**: A PowerShell script that:
  1. Accepts a total duration (e.g., 10 minutes).
  2. Starts `python src/laptop_agents/run.py ... --duration 10`.
  3. Checks the exit code.
  4. **IF** exit code != 0 (crash): Wait 5s, Restart `run.py` with remaining duration.
  5. **IF** exit code == 0: Exit successfully.
- **Verification**: Run `.\scripts\run_autonomous_loop.ps1` for a 2-minute test.

---

## Final Verification
Run the full 10-minute autonomous test:
```powershell
.\scripts\run_autonomous_loop.ps1
```
Expected:
- No crashes (or auto-restart if they occur).
- `final_report.json` generated.
- `summary.html` generated.
- Logs free of specific API keys.
