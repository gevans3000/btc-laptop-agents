import pytest
from pathlib import Path
from laptop_agents.data.providers.backtest_provider import BacktestProvider


def test_backtest_provider_load_csv():
    csv_path = Path("tests/fixtures/sample_candles.csv")
    provider = BacktestProvider(csv_path)

    # history(2) should return first 2
    hist = provider.history(2)
    assert len(hist) == 2
    assert hist[0].ts == "2024-01-01T00:00:00Z"
    assert hist[1].open == 40050.0


@pytest.mark.asyncio
async def test_backtest_provider_listen():
    csv_path = Path("tests/fixtures/sample_candles.csv")
    provider = BacktestProvider(csv_path)

    # listen(start_after=3) should yield remaining 2
    candles = []
    async for c in provider.listen(start_after=3):
        candles.append(c)

    assert len(candles) == 2
    assert candles[0].ts == "2024-01-01T00:03:00Z"
    assert candles[1].close == 40450.0
