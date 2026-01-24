from laptop_agents.paper.broker import PaperBroker
from laptop_agents.trading.helpers import Candle


def test_partial_fill_creates_working_order():
    # Use high fees/slip to ensure we don't accidentally fill everything if volume is low
    broker = PaperBroker(symbol="BTCUSDT", fees_bps=0, slip_bps=0)
    broker.min_trade_interval_sec = 0  # Disable throttle for test

    # Create a candle with low volume to force partial fill
    # Volume is 0.1, max fill is 10% = 0.01
    candle = Candle(
        ts="2024-01-01T00:00:00",
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=0.1,
    )

    order = {
        "go": True,
        "side": "LONG",
        "entry_type": "market",
        "entry": 100.0,
        "qty": 0.05,  # Request 0.05 (stays under 0.1 cap)
        "sl": 99.0,
        "tp": 102.0,
        "equity": 10000.0,
        "client_order_id": "test_partial_001",
    }

    events = broker.on_candle(candle, order)

    import pytest

    # Should have partial fill: qty filled = 0.01
    assert len(events["fills"]) == 1
    assert events["fills"][0].get("partial") is True
    assert events["fills"][0].get("qty") == pytest.approx(0.01)
    assert len(broker.working_orders) == 1
    assert broker.working_orders[0]["qty"] == pytest.approx(0.04)


def test_working_order_fills_on_next_candle():
    broker = PaperBroker(symbol="BTCUSDT", fees_bps=0, slip_bps=0)
    broker.min_trade_interval_sec = 0

    # Candle 1: Partial fill
    candle1 = Candle(
        ts="2024-01-01T00:00:00",
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=0.1,
    )
    order = {
        "go": True,
        "side": "LONG",
        "entry_type": "market",
        "entry": 100.0,
        "qty": 0.05,
        "sl": 90.0,
        "tp": 120.0,
        "equity": 10000.0,
        "client_order_id": "test_wo_001",
    }
    broker.on_candle(candle1, order)
    assert len(broker.working_orders) == 1

    # Close position so working order can fill (PaperBroker only allows 1 pos)
    broker.pos = None  # type: ignore

    # Candle 2: High volume, should fill the rest
    candle2 = Candle(
        ts="2024-01-01T00:01:00",
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=100.0,
    )
    events = broker.on_candle(candle2, None)

    import pytest

    assert len(events["fills"]) == 1
    assert events["fills"][0]["qty"] == pytest.approx(0.04)
    assert len(broker.working_orders) == 0
