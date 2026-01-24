import pytest
from laptop_agents.agents.execution_risk import ExecutionRiskSentinelAgent
from laptop_agents.agents.state import State


@pytest.fixture
def base_state():
    state = State(instrument="BTCUSDT", timeframe="1m")
    state.setup = {
        "name": "TEST_SETUP",
        "side": "LONG",
        "entry_type": "market",
        "sl": 90000.0,
        "tp": 110000.0,
    }
    state.derivatives = {"flags": []}
    # Add dummy candles to pass cooldown check
    from laptop_agents.indicators import Candle

    dummy_candle = Candle("2026-01-01T00:00:00Z", 100, 110, 90, 105, 10)
    state.candles = [dummy_candle] * 10
    state.meta["last_trade_bar"] = 0
    return state


@pytest.fixture
def risk_cfg():
    return {
        "rr_min": 1.5,
        "equity": 10000.0,
        "risk_pct": 1.0,
    }


def test_default_limits(base_state, risk_cfg):
    """Test that missing instrument info results in NO-GO."""
    agent = ExecutionRiskSentinelAgent(risk_cfg)
    new_state = agent.run(base_state)

    assert new_state.order["go"] is False
    assert new_state.order["reason"] == "missing_instrument_info_for_limits"


def test_dynamic_limits(base_state, risk_cfg):
    """Test that provided instrument info overrides defaults."""
    instrument_info = {
        "lotSize": 0.1,
        "minNotional": 10.0,
        "tickSize": 0.5,
        "minQty": 0.1,
        "maxQty": 500.0,
    }
    agent = ExecutionRiskSentinelAgent(risk_cfg, instrument_info=instrument_info)
    new_state = agent.run(base_state)

    assert new_state.order["go"] is True
    assert new_state.order["lot_step"] == 0.1
    assert new_state.order["min_notional"] == 10.0


def test_partial_instrument_info(base_state, risk_cfg):
    """Test that partial info results in NO-GO."""
    instrument_info = {
        "lotSize": 0.5
        # minNotional missing
    }
    agent = ExecutionRiskSentinelAgent(risk_cfg, instrument_info=instrument_info)
    new_state = agent.run(base_state)

    assert new_state.order["go"] is False
    assert new_state.order["reason"] == "missing_instrument_info_for_limits"
