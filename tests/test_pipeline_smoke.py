from pathlib import Path
from laptop_agents.data.providers import MockProvider
from laptop_agents.agents import State, Supervisor
from laptop_agents.indicators import Candle
import json


def test_pipeline_smoke(tmp_path):
    cfg = json.loads(Path("config/default.json").read_text(encoding="utf-8"))
    journal = tmp_path / "paper_journal.jsonl"

    provider = MockProvider(seed=7, start=100_000.0)
    sup = Supervisor(provider=provider, cfg=cfg, journal_path=str(journal))

    state = State(instrument=cfg["instrument"], timeframe=cfg["timeframe"])

    for mc in provider.history(120):
        c = Candle(ts=mc.ts, open=mc.open, high=mc.high, low=mc.low, close=mc.close, volume=mc.volume)
        state = sup.step(state, c)

    assert journal.exists()
    content = journal.read_text(encoding="utf-8").strip().splitlines()
    assert len(content) > 0
