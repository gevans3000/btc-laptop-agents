import pytest
from unittest.mock import MagicMock
from laptop_agents.agents.state import State
from laptop_agents.trading.helpers import Candle
from laptop_agents.agents.market_intake import MarketIntakeAgent
from laptop_agents.agents.derivatives_flows import DerivativesFlowsAgent
from laptop_agents.agents.cvd_divergence import CvdDivergenceAgent
from laptop_agents.agents.setup_signal import SetupSignalAgent
from laptop_agents.agents.execution_risk import ExecutionRiskSentinelAgent
from laptop_agents.agents.risk_gate import RiskGateAgent


@pytest.fixture
def base_candles():
    return [
        Candle(
            ts="2024-01-01T00:00:00Z",
            open=40000,
            high=40100,
            low=39900,
            close=40050,
            volume=10,
        ),
        Candle(
            ts="2024-01-01T00:01:00Z",
            open=40050,
            high=40200,
            low=40000,
            close=40150,
            volume=12,
        ),
    ]


@pytest.fixture
def base_state(base_candles):
    return State(instrument="BTCUSDT", timeframe="1m", candles=base_candles)


def test_market_intake_run(base_state):
    agent = MarketIntakeAgent()
    # Ensure indicators have enough data by padding candles
    for i in range(55):
        base_state.candles.append(
            Candle(
                ts=f"T{i}", open=40000, high=40100, low=39900, close=40050, volume=10
            )
        )

    result = agent.run(base_state)
    assert "price" in result.market_context
    assert "trend" in result.market_context
    assert "regime" in result.market_context


def test_derivatives_flows_run(base_state):
    provider = MagicMock()
    provider.snapshot_derivatives.return_value = {
        "funding_8h": 0.0001,
        "open_interest": 1000000,
    }
    gates = {
        "extreme_funding_8h": 0.001,
        "no_trade_funding_8h": 0.0005,
        "half_size_funding_8h": 0.0003,
    }
    agent = DerivativesFlowsAgent(provider, gates)

    result = agent.run(base_state)
    assert result.derivatives["funding_8h"] == 0.0001
    assert "flags" in result.derivatives


def test_cvd_divergence_run(base_state):
    # Add enough candles for lookback
    for i in range(25):
        base_state.candles.append(
            Candle(
                ts=f"T{i}", open=40000, high=40100, low=39900, close=40050, volume=10
            )
        )

    agent = CvdDivergenceAgent({"lookback": 20})
    result = agent.run(base_state)
    assert "cvd" in result.cvd_divergence
    assert "divergence" in result.cvd_divergence


def test_setup_signal_run(base_state):
    base_state.market_context = {
        "price": 40150,
        "trend": "UP",
        "ema20": 40000,
        "atr": 200,
    }
    cfg = {
        "pullback_ribbon": {
            "enabled": True,
            "entry_band_pct": 0.001,
            "stop_atr_mult": 2.0,
            "tp_r_mult": 3.0,
        },
        "sweep_invalidation": {"enabled": False},
    }
    agent = SetupSignalAgent(cfg)
    result = agent.run(base_state)
    assert result.setup["name"] == "pullback_ribbon"
    assert result.setup["side"] == "LONG"


def test_risk_gate_run(base_state):
    agent = RiskGateAgent({"max_risk": 0.02})

    # Test block by flag
    base_state.derivatives = {"flags": ["NO_TRADE_funding_hot"]}
    base_state.order = {"go": True}
    result = agent.run(base_state)
    assert result.order["go"] is False
    assert "risk_gate_blocked" in result.order["reason"]

    # Test block by risk_pct
    base_state.derivatives = {"flags": []}
    base_state.order = {"go": True, "risk_pct": 0.05}
    result = agent.run(base_state)
    assert result.order["go"] is False


def test_execution_risk_sentinel_run(base_state):
    risk_cfg = {"rr_min": 2.0, "equity": 10000, "risk_pct": 0.01}
    inst_info = {"lotSize": 0.001, "minNotional": 5.0}
    agent = ExecutionRiskSentinelAgent(risk_cfg, inst_info)

    base_state.setup = {
        "name": "test_setup",
        "side": "LONG",
        "entry_type": "market",
        "sl": 39000,
        "tp": 42000,
    }
    # Add enough candles to bypass cooldown (current_bar - 0 >= 5)
    for i in range(10):
        base_state.candles.append(
            Candle(
                ts=f"T{i}", open=40000, high=40100, low=39900, close=40050, volume=10
            )
        )

    result = agent.run(base_state)
    assert result.order["go"] is True
    assert result.order["risk_pct"] == 0.01
    assert result.order["equity"] == 10000
