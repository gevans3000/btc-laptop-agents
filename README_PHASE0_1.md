# BTC Laptop Agents — Phase 0/1 Pack (Bitunix-first)

This pack is designed to get you to:
1) Confirm Bitunix market data works from your laptop (Phase 0)
2) Start collecting 5m BTC candles, backtest a baseline strategy, and run a live paper loop (Phase 1 scaffolding)

## Files
- scripts/bitunix_probe.py
- scripts/collect_candles.py
- scripts/backtest_breakout_ema_atr.py
- scripts/live_paper_loop.py

## Run order
### Phase 0: Probe Bitunix
```powershell
python scripts/bitunix_probe.py --repeats 3
```
Paste output back into ChatGPT.

### Phase 1A: Build a local dataset (no deep pagination)
```powershell
python scripts/collect_candles.py --out data/btcusdt_5m.csv --minutes 30
```

### Phase 1B: Backtest baseline strategy
```powershell
python scripts/backtest_breakout_ema_atr.py --in data/btcusdt_5m.csv --outdir reports
```

### Phase 1C: Live paper loop (writes JSONL journal + state)
```powershell
python scripts/live_paper_loop.py --journal data/paper_journal.jsonl --state data/paper_state.json
```

## Next
Once we confirm Bitunix status (GREEN/YELLOW/RED), we integrate this into your agent/orchestrator cleanly,
and add: ProviderRouter cooldown, durable task queue, and Windows startup scheduling.
