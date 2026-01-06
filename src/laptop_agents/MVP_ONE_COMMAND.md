# MVP_ONE_COMMAND (Laptop Paper Trading)

## Goal (Definition of “Works”)
Running **one command** must reliably produce **one HTML result** (plus raw logs) with minimal compute and minimal code.

Command:
- `python -m laptop_agents.run`

Outputs (always created):
- `runs/latest/summary.html`  ← main thing I open
- `runs/latest/trades.csv`
- `runs/latest/events.jsonl`
- `runs/latest/state.json`

If this works, everything else (agents, dashboards, buttons, async, DI) is optional.

---

## Absolute Minimum Architecture (No Agents, No Event Bus)
This is a **function pipeline**, not a framework.

### Files (tiny set)
- `src/laptop_agents/run.py`  
  Entry point. Orchestrates the run loop.

- `src/laptop_agents/data.py`  
  `load_candles(config) -> list[dict]`  
  (Can use live provider OR a local fixture for testing)

- `src/laptop_agents/strategy.py`  
  `signal(candles, config) -> dict | None`  
  Returns: `{side, entry, sl, tp}` or `None`

- `src/laptop_agents/broker_paper.py`  
  `fill(signal, candles, config) -> trade`  
  Simulate fills with simple assumptions (instant fill or next candle open)

- `src/laptop_agents/report.py`  
  `render_html(run_dir, summary, trades, tail_events) -> summary.html`

- `src/laptop_agents/io.py`  
  `append_event(run_dir, obj)` writes JSONL  
  `save_state(run_dir, state)` writes JSON

That’s it.

---

## Run Loop (Deterministic Steps)
1) Create run dir: `runs/latest/` (wipe + recreate)
2) Load config (defaults ok)
3) Load candles (N candles)
4) Append event: `RunStarted`
5) Compute signal (or None)
6) If signal:
   - Simulate order fill
   - Update position/PnL
   - Append event: `TradeSimulated`
7) Write `trades.csv`
8) Write `state.json`
9) Render `summary.html`
10) Append event: `RunFinished`

No retries. No scheduling. No background. No multi-agent.

---

## Data Model (Keep It Stupid Simple)

### events.jsonl (append-only)
Each line is a JSON object:
- `ts` (ISO string)
- `type` (RunStarted, MarketDataLoaded, SignalGenerated, TradeSimulated, Error, RunFinished)
- `run_id`
- `payload` (small dict)

### trades.csv (flat, human-friendly)
Columns:
- trade_id, ts_open, ts_close, side, entry, exit, qty, pnl, fees, reason

### state.json (current snapshot)
- run_id
- starting_balance
- ending_balance
- open_position (or null)
- totals: trades, wins, losses, pnl, fees
- last_event_ts

---

## HTML Report (Simple + Fast)
`summary.html` shows:
- Starting balance / Ending balance / Net PnL
- Trades count / Win rate
- Trades table (last 50)
- Events tail (last 100)
- Any errors (if present)

No JS frameworks. No charts required (optional later).

---

## “Run Twice” (Optional but still simple)
Add a flag:
- `python -m laptop_agents.run --twice`

Creates:
- `runs/run_001/summary.html`
- `runs/run_002/summary.html`
- `runs/index.html` linking both

---

## Non-Goals (Explicitly Not Now)
These are banned until MVP works:
- DI container
- event bus / async pub-sub
- multi-agent orchestration
- dashboard buttons/UI
- metrics/tracing systems
- CI/CD expansion

---

## Success Checklist
- [ ] The command runs without manual steps
- [ ] `summary.html` opens and clearly shows PnL + trades
- [ ] `events.jsonl` exists and explains what happened
- [ ] Running it twice produces two clean run folders (optional)

---

## If Something Breaks
The only debugging sources we care about:
1) `runs/latest/events.jsonl`
2) `runs/latest/state.json`
3) stack trace in console

Fix the smallest thing and rerun.

