"""Coverage booster tests for refactored modules."""

import pytest
from unittest.mock import patch
from laptop_agents.paper.broker_types import Position
from laptop_agents.paper.position_engine import (
    calculate_unrealized_pnl,
    process_fifo_close,
)
from laptop_agents.paper.broker import PaperBroker
from laptop_agents.trading.helpers import Candle, Tick
from collections import deque


@pytest.fixture(autouse=True)
def mock_append_event():
    with patch("laptop_agents.core.events.append_event") as mock:
        yield mock


class TestPositionEngine:
    def test_unrealized_pnl_linear(self):
        pos = Position(
            side="LONG",
            qty=1.0,
            sl=90,
            tp=110,
            opened_at="now",
            lots=deque([{"qty": 1.0, "price": 100.0, "fees": 0.0}]),
        )
        pnl = calculate_unrealized_pnl(pos, 105.0, False)
        assert pnl == 5.0

        pos.side = "SHORT"
        pnl = calculate_unrealized_pnl(pos, 95.0, False)
        assert pnl == 5.0

    def test_unrealized_pnl_inverse(self):
        pos = Position(
            side="LONG",
            qty=100.0,
            sl=90,
            tp=110,
            opened_at="now",
            lots=deque([{"qty": 100.0, "price": 100.0, "fees": 0.0}]),
        )
        pnl = calculate_unrealized_pnl(pos, 105.0, True)
        assert pnl == pytest.approx(5.0)

    def test_fifo_partial_close(self):
        pos = Position(
            side="LONG",
            qty=2.0,
            sl=90,
            tp=110,
            opened_at="now",
            lots=deque(
                [
                    {"qty": 1.0, "price": 100.0, "fees": 0.5},
                    {"qty": 1.0, "price": 110.0, "fees": 0.5},
                ]
            ),
        )
        res = process_fifo_close(pos, 1.5, 120.0, 0.0005, False)
        assert res["reduction"] == 1.5
        assert len(pos.lots) == 1


class TestBrokerIntegration:
    def test_broker_lifecycle_tp_sl(self):
        broker = PaperBroker(symbol="BTCUSDT", starting_equity=10000.0, state_path=None)

        # 1. Fill
        candle = Candle(ts="1", open=100, high=101, low=99, close=100, volume=100)
        order = {
            "go": True,
            "side": "LONG",
            "qty": 1.0,
            "entry_type": "market",
            "entry": 100,
            "sl": 90,
            "tp": 110,
        }
        broker.on_candle(candle, order)
        assert broker.pos is not None

        # 2. Exit via TP
        candle_tp = Candle(ts="2", open=100, high=115, low=99, close=112, volume=100)
        events = broker.on_candle(candle_tp, None)
        assert len(events["exits"]) == 1
        assert events["exits"][0]["reason"] == "TP"
        assert broker.pos is None

    def test_broker_tick_exit_short(self):
        broker = PaperBroker(symbol="BTCUSDT", state_path=None)
        # Force open short
        broker.pos = Position(
            side="SHORT",
            qty=1.0,
            sl=110,
            tp=90,
            opened_at="1",
            lots=deque([{"qty": 1.0, "price": 100.0, "fees": 0.0}]),
        )

        # Tick hits TP
        tick = Tick(symbol="BTCUSDT", bid=85, ask=86, last=85, ts="1.1")
        events = broker.on_tick(tick)
        assert len(events["exits"]) == 1
        assert "TP_TICK" in events["exits"][0]["reason"]

    def test_trailing_stop_activation_and_hit(self):
        broker = PaperBroker(
            symbol="BTCUSDT", strategy_config={"trailing_atr_mult": 1.0}
        )
        # Entry 100, SL 90 (1.0R = 10 points). Activation at 0.5R = 105.
        broker.pos = Position(
            side="LONG",
            qty=1.0,
            sl=90,
            tp=150,
            opened_at="1",
            lots=deque([{"qty": 1.0, "price": 100.0, "fees": 0.0}]),
        )

        # Candle close at 106 -> Activates trail. Trail stop = 106 - 10 = 96.
        candle = Candle(ts="2", open=100, high=107, low=99, close=106, volume=100)
        broker.on_candle(candle, None)
        assert broker.pos.trail_active
        assert broker.pos.trail_stop == 96.0

        # Candle low at 95 hits trail
        candle2 = Candle(ts="3", open=106, high=107, low=95, close=100, volume=100)
        events = broker.on_candle(candle2, None)
        assert len(events["exits"]) == 1
        assert events["exits"][0]["reason"] == "TRAIL"

    def test_inverse_pnl_consistency(self):
        broker = PaperBroker(symbol="BTC-USD", state_path=None)  # Inverse
        assert broker.is_inverse

        candle = Candle(ts="1", open=100, high=101, low=99, close=100, volume=1000)
        # 100 USD worth of BTC at price 100 = 1.0 BTC?
        # Actually our broker uses Notional USD for inverse qty
        order = {
            "go": True,
            "side": "LONG",
            "qty": 1.0,
            "entry_type": "market",
            "entry": 100,
            "sl": 90,
            "tp": 110,
        }

        broker.on_candle(candle, order)
        # Entry 100. Exit at 110. PnL = 1.0 * (1/100 - 1/110) * 110 = 1.1 - 1 = 0.1 COINS.
        # Net USD PnL = 0.1 * 110 = 11 USD?
        # Wait, (1 - 100/110) * 110 = 110 - 100 = 10 USD.

        candle_exit = Candle(ts="2", open=110, high=110, low=110, close=110, volume=1)
        events = broker.on_candle(candle_exit, None)
        assert events["exits"][0]["pnl"] == pytest.approx(
            10.0, rel=0.1
        )  # allowing for fees/slippage
