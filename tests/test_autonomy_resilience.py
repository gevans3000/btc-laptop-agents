from unittest.mock import MagicMock
from laptop_agents.paper.broker import PaperBroker


def test_paper_broker_idempotency():
    broker = PaperBroker()
    candle = MagicMock()
    candle.close = 50000.0
    candle.low = 49000.0
    candle.high = 51000.0
    candle.ts = "2024-01-01T00:00:00Z"
    candle.volume = 1000.0

    order = {
        "go": True,
        "side": "LONG",
        "qty": 0.01,
        "entry": 50000.0,
        "entry_type": "limit",
        "sl": 49000.0,
        "tp": 51000.0,
        "client_order_id": "test_id_1",
    }

    # First call
    res1 = broker._try_fill(candle, order)
    assert res1 is not None
    assert broker.pos is not None

    # Second call with same ID
    res2 = broker._try_fill(candle, order)
    assert res2 == res1
    assert broker.pos.qty == 0.01


def test_paper_broker_position_cap():
    broker = PaperBroker(symbol="BTCUSDT")
    broker.max_position_per_symbol = {"BTCUSDT": 0.05}

    candle = MagicMock()
    candle.close = 50000.0
    candle.low = 49000.0
    candle.high = 51000.0

    order = {"qty": 0.1, "side": "LONG", "entry_type": "market"}
    res = broker._try_fill(candle, order)
    assert res is None


def test_paper_broker_slippage_and_fees():
    broker = PaperBroker(slip_bps=10.0)
    broker.max_position_per_symbol = {"BTCUSDT": 1.0}
    broker.exchange_fees = {"maker": 0.0, "taker": 0.0005}

    candle = MagicMock()
    candle.close = 50000.0
    candle.low = 49000.0
    candle.high = 51000.0
    candle.ts = "2024-01-01T00:00:00Z"
    candle.volume = 1000.0

    order = {
        "go": True,
        "side": "LONG",
        "qty": 0.01,
        "entry_type": "market",
        "entry": 50000.0,
        "sl": 40000.0,
        "tp": 60000.0,
    }
    res = broker._try_fill(candle, order)

    assert res is not None
    # 30bps slip: 50000 * 1.0003 = 50015
    assert res["price"] >= 50015.0
    assert res["fees"] == (res["price"] * 0.01 * 0.0005)


def test_paper_broker_fifo():
    broker = PaperBroker()
    broker.max_position_per_symbol = {"BTCUSDT": 100.0}
    broker.min_trade_interval_sec = 0.0
    broker.exchange_fees = {"maker": 0.0, "taker": 0.0}

    candle = MagicMock()
    candle.close = 50000.0
    candle.low = 40000.0
    candle.high = 60000.0
    candle.ts = "2024-01-01T00:00:00Z"
    candle.volume = 1000.0

    # Entry 1
    broker._try_fill(
        candle,
        {
            "go": True,
            "side": "LONG",
            "qty": 0.001,
            "entry_type": "limit",
            "entry": 50000.0,
            "sl": 40000.0,
            "tp": 60000.0,
        },
    )
    # Entry 2
    candle.close = 51000.0
    broker._try_fill(
        candle,
        {
            "go": True,
            "side": "LONG",
            "qty": 0.001,
            "entry_type": "limit",
            "entry": 51000.0,
            "sl": 40000.0,
            "tp": 60000.0,
        },
    )

    assert broker.pos is not None
    assert broker.pos.qty == 0.002
    assert abs(broker.pos.entry - 50500.0) < 1.0

    # Exit
    exit_px = 52000.0
    res = broker._exit("2024-01-01T00:01:00Z", exit_px, "TP")

    assert abs(res["pnl"] - 3.0) < 0.1
