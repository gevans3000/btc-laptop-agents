from pathlib import Path
from laptop_agents.data.providers import MockProvider
from laptop_agents.agents import State as AgentState, Supervisor
from laptop_agents.indicators import Candle
import json


def test_pipeline_smoke(tmp_path):
    temp_dir = tmp_path
    from laptop_agents.core.config_models import StrategyConfig, EngineConfig, RiskConfig
    cfg = StrategyConfig(
        engine=EngineConfig(pending_trigger_max_bars=5, derivatives_refresh_bars=6),
        derivatives_gates={},
        setups={
            "default": {"active": True, "params": {}},
            "pullback_ribbon": {"enabled": False},
            "sweep_invalidation": {"enabled": False}
        },
        risk=RiskConfig(risk_pct=1.0, rr_min=1.5),
        cvd={}
    ).model_dump()
    journal = temp_dir / "paper_journal.jsonl"

    provider = MockProvider(seed=7, start=100_000.0)
    sup = Supervisor(provider=provider, cfg=cfg, journal_path=str(journal))

    state = AgentState(
        instrument=cfg.get("instrument", "BTCUSDT"),
        timeframe=cfg.get("timeframe", "1h")
    )

    for mc in provider.history(500):
        c = Candle(ts=mc.ts, open=mc.open, high=mc.high, low=mc.low, close=mc.close, volume=mc.volume)
        state = sup.step(state, c)

    assert journal.exists()
