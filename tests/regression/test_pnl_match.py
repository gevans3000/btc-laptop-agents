import pytest
import json
from pathlib import Path
from laptop_agents.core.config_loader import load_profile
from laptop_agents.session.backtest_session import run_backtest_session


def load_json(path):
    with open(path, "r") as f:
        return json.load(f)


@pytest.mark.asyncio
@pytest.mark.parametrize("dataset", ["dataset_1"])
async def test_pnl_matches_baseline(dataset):
    csv_path = Path(f"tests/fixtures/baselines/{dataset}.csv")
    expected_path = Path(f"tests/fixtures/baselines/{dataset}_expected.json")

    overrides = {"data": {"path": str(csv_path)}, "engine": {"warmup_candles": 2}}
    config = load_profile("backtest", cli_overrides=overrides)

    stats = await run_backtest_session(config)
    expected = load_json(expected_path)

    assert abs(stats["net_pnl"] - expected["net_pnl"]) < 0.01
    assert stats["total_trades"] == expected["total_trades"]
