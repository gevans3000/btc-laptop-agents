from laptop_agents.backtest.funding import FundingLoader
from pathlib import Path


def test_funding_loader():
    csv_path = Path("data/funding/BTCUSDT_funding.csv")
    loader = FundingLoader(csv_path)

    rate = loader.get_rate_at("2024-01-01T08:00:00Z")
    assert rate == 0.0001

    rate = loader.get_rate_at("2024-01-01T00:00:00Z")
    assert rate == 0.0001
