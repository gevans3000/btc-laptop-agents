from laptop_agents.resilience.error_circuit_breaker import (
    ErrorCircuitBreaker,
)
from unittest.mock import MagicMock
from laptop_agents import constants as hard_limits
from laptop_agents.execution.bitunix_broker import BitunixBroker
import time


def test_circuit_breaker_failures():
    cb = ErrorCircuitBreaker(failure_threshold=2, recovery_timeout=1, time_window=1)

    def failing_func():
        raise ValueError("Failed")

    def success_func():
        return "Success"

    # First fail
    cb.record_failure()
    assert cb.state == "CLOSED"

    # Second fail -> Open
    cb.record_failure()
    assert cb.state == "OPEN"

    # Call while open
    assert not cb.allow_request()

    # Wait for recovery
    time.sleep(1.1)
    assert cb.allow_request()  # Should be in HALF_OPEN state now

    # Success in half-open -> Close
    cb.record_success()
    assert cb.state == "CLOSED"


def test_hard_limit_max_notional(monkeypatch):
    # Mock Provider
    provider = MagicMock()
    provider.symbol = "BTCUSDT"
    provider.fetch_instrument_info.return_value = {
        "tickSize": 0.1,
        "lotSize": 0.001,
        "minQty": 0.001,
    }

    # Monkeypatch to a tiny limit so the $10 order exceeds it
    monkeypatch.setattr(hard_limits, "MAX_POSITION_SIZE_USD", 5.0)

    broker = BitunixBroker(provider)

    # Mock Candle
    candle = MagicMock()
    candle.ts = "2024-01-01T00:00:00Z"
    candle.close = 50000.0

    # Order (qty will be recalculated to ~$10 by broker)
    order = {
        "go": True,
        "side": "LONG",
        "qty": 0.1,
        "entry": 50000.0,
        "equity": 10000.0,
    }

    events = broker.on_candle(candle, order)

    # Verify error is reported (Fixed $10 > $5 limit)
    assert any("REJECTED: Order notional" in err for err in events["errors"])
    provider.place_order.assert_not_called()


def test_kill_switch_enforcement(monkeypatch):
    # 1. Setup Mock Provider with valid instrument info
    provider = MagicMock()
    provider.symbol = "BTCUSDT"
    provider.fetch_instrument_info.return_value = {
        "tickSize": 0.1,
        "lotSize": 0.001,
        "minQty": 0.001,
    }
    broker = BitunixBroker(provider)

    # 2. Mock Candle
    candle = MagicMock()
    candle.close = 50000.0
    candle.ts = "2024-01-01T00:00:00Z"

    # 3. Set Kill Switch via Environment (Single Source of Truth)
    monkeypatch.setenv("LA_KILL_SWITCH", "TRUE")

    order = {"go": True, "side": "LONG", "qty": 0.001}

    # 4. Execute
    events = broker.on_candle(candle, order)

    # 5. Verify
    assert "KILL_SWITCH_ACTIVE" in events["errors"]
    provider.place_order.assert_not_called()


def test_kill_switch_off_enforcement(monkeypatch):
    """Ensure trading proceeds when kill switch is OFF."""
    provider = MagicMock()
    provider.symbol = "BTCUSDT"
    provider.fetch_instrument_info.return_value = {
        "tickSize": 0.1,
        "lotSize": 0.001,
        "minQty": 0.001,
    }
    broker = BitunixBroker(provider)

    candle = MagicMock()
    candle.close = 50000.0
    candle.ts = "2024-01-01T00:00:00Z"

    # Kill switch OFF
    monkeypatch.setenv("LA_KILL_SWITCH", "FALSE")
    monkeypatch.setenv("SKIP_LIVE_CONFIRM", "TRUE")  # Avoid input()

    order = {
        "go": True,
        "side": "LONG",
        "qty": 0.001,
        "entry": 50000.0,
        "sl": 49000.0,
        "tp": 52000.0,
    }

    broker.on_candle(candle, order)

    # Verify order was placed
    provider.place_order.assert_called_once()
