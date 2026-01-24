"""Unit tests for BitunixBroker with mocked provider."""

import pytest
from unittest.mock import MagicMock
from laptop_agents.execution.bitunix_broker import BitunixBroker
from laptop_agents.trading.helpers import Candle
from datetime import datetime


@pytest.fixture
def mock_provider():
    provider = MagicMock()
    provider.symbol = "BTCUSDT"
    provider.fetch_instrument_info.return_value = {
        "tickSize": 0.01,
        "lotSize": 0.001,
        "minQty": 0.001,
    }
    provider.get_pending_positions.return_value = []
    return provider


@pytest.fixture
def broker(mock_provider):
    return BitunixBroker(provider=mock_provider, starting_equity=10000.0)


def make_candle(close=50000.0):
    return Candle(
        ts=datetime.now().isoformat(),
        open=close,
        high=close + 10,
        low=close - 10,
        close=close,
        volume=100,
    )


def test_broker_init(broker):
    assert broker.symbol == "BTCUSDT"
    assert broker.starting_equity == 10000.0


def test_no_order_no_action(broker):
    candle = make_candle()
    events = broker.on_candle(candle, None)
    assert events["fills"] == []
    assert events["exits"] == []


def test_rate_limit_enforcement(broker):
    from laptop_agents import constants

    candle = make_candle()
    order = {
        "go": True,
        "side": "LONG",
        "qty": 0.01,
        "entry": 50000,
        "sl": 49000,
        "tp": 52000,
        "equity": 10000,
    }
    # Exhaust rate limit
    for _ in range(constants.MAX_ORDERS_PER_MINUTE + 1):
        broker.on_candle(candle, order)
    # Should have errors
    broker.on_candle(candle, order)
    assert len(broker.order_timestamps) <= constants.MAX_ORDERS_PER_MINUTE


def test_kill_switch_blocks_orders(broker, monkeypatch):
    monkeypatch.setenv("LA_KILL_SWITCH", "TRUE")
    candle = make_candle()
    order = {"go": True, "side": "LONG", "qty": 0.01}
    events = broker.on_candle(candle, order)
    assert "KILL_SWITCH_ACTIVE" in events.get("errors", [])
