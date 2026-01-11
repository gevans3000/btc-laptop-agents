import unittest
from unittest.mock import MagicMock
from laptop_agents.resilience.circuit import CircuitBreaker, CircuitBreakerOpenError
from laptop_agents.core import hard_limits
from laptop_agents.execution.bitunix_broker import BitunixBroker
from laptop_agents.resilience.errors import SafetyException
import time
import os

class TestSafetyManual(unittest.TestCase):
    def test_circuit_breaker_failures(self):
        cb = CircuitBreaker(max_failures=2, reset_timeout=1)
        
        def failing_func():
            raise ValueError("Failed")
            
        def success_func():
            return "Success"

        # First fail
        try:
            cb.guarded_call(failing_func)
        except ValueError:
            pass
        self.assertEqual(cb.state, "CLOSED")
        self.assertEqual(cb.failures, 1)

        # Second fail -> Open
        try:
            cb.guarded_call(failing_func)
        except ValueError:
            pass
        self.assertEqual(cb.state, "OPEN")
        self.assertEqual(cb.failures, 2)

        # Call while open
        with self.assertRaises(CircuitBreakerOpenError):
            cb.guarded_call(success_func)

        # Recovery
        time.sleep(1.1)
        # Should be HALF_OPEN now upon call
        self.assertEqual(cb.guarded_call(success_func), "Success")
        self.assertEqual(cb.state, "CLOSED")
        self.assertEqual(cb.failures, 0)

    def test_hard_limit_max_notional(self):
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
        
        # Order that exceeds limit ($200,000)
        # 10 BTC at 50,000 = $500,000
        order = {
            "go": True,
            "side": "LONG",
            "qty": 10.0,
            "entry": 50000.0
        }
        
        events = broker.on_candle(candle, order)
        
        # Verify error is reported and no order submitted
        errors = events.get("errors", [])
        self.assertTrue(any("REJECTED: Order notional" in err for err in errors), f"Expected rejection error, got: {errors}")
        provider.place_order.assert_not_called()

if __name__ == '__main__':
    unittest.main()
