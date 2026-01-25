import os
from unittest.mock import patch
from laptop_agents.core.config_loader import load_profile


def test_load_profile_merges_base():
    config = load_profile("backtest")
    assert config["symbol"] == "BTCUSDT"
    assert config["mode"] == "backtest"
    assert config["broker"]["type"] == "backtest"


def test_load_profile_cli_overrides():
    cli_overrides = {"trading": {"risk_pct": 2.0}}
    config = load_profile("backtest", cli_overrides=cli_overrides)
    assert config["trading"]["risk_pct"] == 2.0
    assert config["symbol"] == "BTCUSDT"


def test_load_profile_env_overrides():
    with patch.dict(os.environ, {"LA_TRADING_RISK_PCT": "5.0"}):
        config = load_profile("backtest")
        assert config["trading"]["risk_pct"] == 5.0
