from dataclasses import dataclass
from laptop_agents.backtest.backtest_broker import BacktestBroker
from laptop_agents.core.protocols import BrokerProtocol


@dataclass
class MockCandle:
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 1000.0


def test_backtest_broker_implements_protocol():
    broker = BacktestBroker()
    assert isinstance(broker, BrokerProtocol)


def test_backtest_broker_fill_market():
    broker = BacktestBroker(starting_equity=10000.0)
    candle = MockCandle("2024-01-01T00:00:00Z", 40000, 41000, 39000, 40500)
    order = {"side": "LONG", "qty": 0.1, "go": True, "entry_type": "market"}

    events = broker.on_candle(candle, order)
    assert len(events["fills"]) == 1
    assert broker.pos is not None
    assert broker.pos.qty == 0.1
    assert broker.pos.side == "LONG"


def test_backtest_broker_sl_hit():
    broker = BacktestBroker(starting_equity=10000.0)
    candle1 = MockCandle("2024-01-01T00:00:00Z", 40000, 41000, 39000, 40500)
    order = {
        "side": "LONG",
        "qty": 1.0,
        "go": True,
        "entry_type": "market",
        "sl": 38000,
        "tp": 45000,
    }

    broker.on_candle(candle1, order)

    candle2 = MockCandle("2024-01-01T00:01:00Z", 40000, 40500, 37000, 39000)
    events = broker.on_candle(candle2, None)

    assert len(events["exits"]) == 1
    assert events["exits"][0]["reason"] == "SL"
    assert broker.pos is None
    assert broker.current_equity < 10000.0
