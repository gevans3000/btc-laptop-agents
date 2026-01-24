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
    state.candles = [1] * 10
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
    """Test that default limits are used when no instrument info is provided."""
    agent = ExecutionRiskSentinelAgent(risk_cfg)
    new_state = agent.run(base_state)

    assert new_state.order["go"] is True
    assert new_state.order["lot_step"] == 0.001
    assert new_state.order["min_notional"] == 5.0


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
    """Test that partial info falls back to defaults for missing keys."""
    instrument_info = {
        "lotSize": 0.5
        # minNotional missing
    }
    agent = ExecutionRiskSentinelAgent(risk_cfg, instrument_info=instrument_info)
    new_state = agent.run(base_state)

    assert new_state.order["go"] is True
    assert new_state.order["lot_step"] == 0.5
    assert new_state.order["min_notional"] == 5.0  # Default
