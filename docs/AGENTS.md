# AGENTS.md — BTC Laptop Agents (Paper Trading) Collaboration

## Non-negotiables
- Paper-only. Never place real orders.
- Minimal diffs. No refactors/renames unless required.
- No hangs: any network call must have timeouts.
- Always validate: `python -m compileall src` and `pytest -q`
- Persist artifacts:
  - logs/events.jsonl (ops + resilience)
  - data/paper_journal.jsonl (paper actions)
  - data/paper_state.json (state)
  - data/control.json (pause/extend)

## MVP Definition of Done
`.\scripts\start_live_paper.ps1` runs unattended and:
- logs at least 1 JSONL line per loop
- writes paper journal + state to data/
- survives provider/network errors without crashing
- records paper entries/exits with PnL/R

## Logical agents (implementation can be functions/modules)
1) Supervisor (Loop owner): scheduling + exception boundary + heartbeat
2) Market Intake: provider fetch (Bitunix) using resilience wrapper
3) Setup/Signal: deterministic rules (EMA/ATR thresholds)
4) Execution/Risk (paper): sim fills + position mgmt + stats
5) Journal Coach: concise notes per loop/trade (optional)
