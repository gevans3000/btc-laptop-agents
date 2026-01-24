import pytest
import json
from typing import Any
from laptop_agents.trading.exec_engine import (
    _load_or_init_state,
    _open_paper_position,
    _close_paper_position,
)
from laptop_agents.trading.helpers import Candle


@pytest.fixture
def temp_paper_dir(local_tmp_path):
    return local_tmp_path / "paper"


def test_load_or_init_state_new(temp_paper_dir):
    temp_paper_dir.mkdir()
    state = _load_or_init_state(
        temp_paper_dir,
        10000.0,
        "BTCUSDT",
        "1m",
        "mock",
        2.0,
        0.5,
        1.0,
        30.0,
        1.5,
        1.0,
        "conservative",
    )
    assert state["equity"] == 10000.0
    assert state["symbol"] == "BTCUSDT"
    assert state["position"] is None


def test_load_or_init_state_existing(temp_paper_dir):
    temp_paper_dir.mkdir()
    existing_state = {
        "equity": 12000.0,
        "symbol": "BTCUSDT",
        "last_ts": "2024-01-01T00:00:00Z",
    }
    with open(temp_paper_dir / "state.json", "w") as f:
        json.dump(existing_state, f)

    state = _load_or_init_state(
        temp_paper_dir,
        10000.0,
        "BTCUSDT",
        "1m",
        "mock",
        2.0,
        0.5,
        1.0,
        30.0,
        1.5,
        1.0,
        "conservative",
    )
    assert state["equity"] == 12000.0
    assert state["last_ts"] == "2024-01-01T00:00:00Z"


def test_open_paper_position(temp_paper_dir):
    state: dict[str, Any] = {
        "equity": 10000.0,
        "position": None,
        "risk_pct": 1.0,
        "stop_bps": 30.0,
        "tp_r": 1.5,
        "max_leverage": 1.0,
        "slip_bps": 0.5,
        "fees_bps": 2.0,
    }
    candle = Candle(
        ts="2024-01-01T00:00:00Z",
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=10.0,
    )
    events = []

    def append_event(e):
        events.append(e)

    _open_paper_position("LONG", candle, state, append_event)

    assert state["position"] is not None
    assert state["position"]["side"] == "LONG"
    assert len(events) == 1
    assert events[0]["event"] == "PositionOpened"


def test_close_paper_position(temp_paper_dir):
    state = {
        "equity": 10000.0,
        "position": {
            "side": "LONG",
            "entry_price": 100.0,
            "entry_ts": "2024-01-01T00:00:00Z",
            "quantity": 10.0,
            "stop_price": 99.0,
            "tp_price": 101.5,
        },
        "slip_bps": 0.0,
        "fees_bps": 0.0,
        "realized_pnl": 0.0,
    }
    candle = Candle(
        ts="2024-01-01T00:01:00Z",
        open=102.0,
        high=103.0,
        low=101.0,
        close=102.0,
        volume=10.0,
    )
    trades: list[dict[str, Any]] = []
    events = []

    def append_event(e):
        events.append(e)

    _close_paper_position("TP", 101.5, candle, state, trades, append_event)

    assert state["position"] is None
    assert len(trades) == 1
    assert trades[0]["exit_reason"] == "TP"
    assert state["equity"] == 10000.0 + (101.5 - 100.0) * 10.0
