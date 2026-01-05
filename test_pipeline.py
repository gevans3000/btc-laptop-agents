#!/usr/bin/env python3
"""Quick pipeline test to verify everything works."""

from laptop_agents.data.providers import MockProvider
from laptop_agents.agents import State, Supervisor
from laptop_agents.indicators import Candle
import json

# Load config
with open('config/default.json') as f:
    cfg = json.load(f)

# Create mock provider
provider = MockProvider(seed=7, start=100_000.0)

# Create supervisor
sup = Supervisor(provider=provider, cfg=cfg, journal_path='data/test_journal.jsonl')

# Create state
state = State(instrument=cfg['instrument'], timeframe=cfg['timeframe'])

# Run 50 steps
candles = provider.history(50)
for i, mc in enumerate(candles, start=1):
    candle = Candle(ts=mc.ts, open=mc.open, high=mc.high, low=mc.low, close=mc.close, volume=mc.volume)
    state = sup.step(state, candle)
    if i % 10 == 0:
        price = state.market_context.get("price", 0)
        setup_name = state.setup.get("name", "NONE")
        trade_id = state.trade_id or "None"
        print(f"Step {i}: price={price:,.0f} setup={setup_name} trade_id={trade_id}")

print("\nPipeline test completed successfully!")
print(f"Final state: {len(state.candles)} candles processed")
print(f"Journal written to: data/test_journal.jsonl")
