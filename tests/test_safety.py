import pytest
from unittest.mock import MagicMock
from laptop_agents.resilience.circuit import CircuitBreaker, CircuitBreakerOpenError
from laptop_agents.core import hard_limits
from laptop_agents.execution.bitunix_broker import BitunixBroker
from laptop_agents.resilience.errors import SafetyException
import time
import os

def test_circuit_breaker_failures():
    cb = CircuitBreaker(max_failures=2, reset_timeout=1)
    
    def failing_func():
        raise ValueError("Failed")
        
    def success_func():
        return "Success"

    # First fail
    with pytest.raises(ValueError):
        cb.guarded_call(failing_func)
    assert cb.state == "CLOSED"
    assert cb.failures == 1

    # Second fail -> Open
    with pytest.raises(ValueError):
        cb.guarded_call(failing_func)
    assert cb.state == "OPEN"
    assert cb.failures == 2

    # Call while open
    with pytest.raises(CircuitBreakerOpenError):
        cb.guarded_call(success_func)

    # Recovery
    time.sleep(1.1)
    # Should be HALF_OPEN now upon call
    assert cb.guarded_call(success_func) == "Success"
    assert cb.state == "CLOSED"
    assert cb.failures == 0

def test_hard_limit_max_notional():
    # Mock Provider
    provider = MagicMock()
    provider.symbol = "BTCUSDT"
    provider.fetch_instrument_info.return_value = {
        "tickSize": 0.1,
        "lotSize": 0.001
    }
    
    broker = BitunixBroker(provider)
    
    # Mock Candle
    candle = MagicMock()
    candle.ts = 1600000000
    candle.close = 50000.0
    
    # Order that exceeds limit ($1000)
    # 0.1 BTC at 50,000 = $5000
    order = {
        "go": True,
        "side": "LONG",
        "qty": 0.1,
        "entry": 50000.0
    }
    
    events = broker.on_candle(candle, order)
    
    # Verify error is reported and no order submitted
    assert any("REJECTED: Order notional" in err for err in events["errors"])
    provider.place_order.assert_not_called()

def test_kill_switch_enforcement(monkeypatch):
    # Mock Provider
    provider = MagicMock()
    provider.symbol = "BTCUSDT"
    broker = BitunixBroker(provider)
    
    # Mock Candle
    candle = MagicMock()
    
    # Mock os.path.exists to return True for the kill switch file
    monkeypatch.setattr("os.path.exists", lambda p: p == "config/KILL_SWITCH.txt")
    
    # Mock builtins.open
    from unittest.mock import mock_open
    m = mock_open(read_data="TRUE")
    monkeypatch.setattr("builtins.open", m)
    
    order = {"go": True, "side": "LONG", "qty": 0.001}
    
    events = broker.on_candle(candle, order)
    
    assert "KILL_SWITCH_ACTIVE" in events["errors"]
    provider.place_order.assert_not_called()
