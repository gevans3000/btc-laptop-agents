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

    def test_inverse_pnl_calculation(self):
        """Verify BTCUSD Inverse PnL: PnL(BTC) = Notional * (1/Entry - 1/Exit)"""
        from laptop_agents.paper.broker import PaperBroker
        from dataclasses import dataclass
        
        @dataclass
        class MockCandle:
            ts: str = "2026-01-01T00:00:00Z"
            open: float = 90000.0
            high: float = 91000.0
            low: float = 89000.0
            close: float = 90500.0
        
        broker = PaperBroker(symbol="BTCUSD")
        candle = MockCandle()
        
        # Simulate a LONG fill at market (90500)
        # Input qty is 0.01 BTC. Notional = 0.01 * 90500 = 905 USD.
        order = {
            "go": True,
            "side": "LONG",
            "entry_type": "market",
            "entry": 90500.0,
            "qty": 0.01,
            "sl": 89500.0,
            "tp": 92000.0,
            "equity": 10000.0
        }
        events = broker.on_candle(candle, order)
        self.assertEqual(len(events["fills"]), 1, f"Expected 1 fill, got {events}")
        
        # Simulate TP hit (high reaches 92000)
        exit_candle = MockCandle(high=92000.0, low=90000.0)
        events = broker.on_candle(exit_candle, None)
        self.assertEqual(len(events["exits"]), 1, f"Expected 1 exit, got {events}")
        
        exit_event = events["exits"][0]
        # PnL = Notional * (1/Entry - 1/Exit)
        # PnL = 905 * (1/90500 - 1/92000)
        # PnL = 905 * (0.0000110497... - 0.0000108695...)
        # PnL should be positive.
        self.assertGreater(exit_event["pnl"], 0, f"Expected positive PnL for profitable long, got {exit_event['pnl']}")
        self.assertGreater(exit_event["r"], 0, f"Expected positive R-mult, got {exit_event['r']}")
        print(f"Inverse PnL Test Passed: PnL={exit_event['pnl']:.8f} BTC, R={exit_event['r']:.2f}")

if __name__ == '__main__':
    unittest.main()
