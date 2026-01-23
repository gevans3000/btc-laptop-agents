import unittest
from unittest.mock import MagicMock
from laptop_agents.resilience import ErrorCircuitBreaker as CircuitBreaker
from laptop_agents.execution.bitunix_broker import BitunixBroker
import time


class TestSafetyManual(unittest.TestCase):
    def test_circuit_breaker_failures(self):
        cb = CircuitBreaker(failure_threshold=2, time_window=60, recovery_timeout=1)

        # First fail
        cb.record_failure()
        self.assertEqual(cb.state, "CLOSED")
        self.assertTrue(cb.allow_request())

        # Second fail -> Open
        cb.record_failure()
        self.assertEqual(cb.state, "OPEN")
        self.assertFalse(cb.allow_request())

        # Recovery
        time.sleep(1.1)
        # Should be CLOSED now upon successful request
        self.assertTrue(cb.allow_request())
        cb.record_success()
        self.assertEqual(cb.state, "CLOSED")

    def test_hard_limit_max_notional(self):
        # Mock Provider
        provider = MagicMock()
        provider.symbol = "BTCUSDT"
        provider.fetch_instrument_info.return_value = {
            "tickSize": 0.1,
            "lotSize": 0.001,
            "minQty": 0.001,
            "minNotional": 10.0,
        }

        broker = BitunixBroker(provider)

        # Mock Candle
        candle = MagicMock()
        candle.ts = 1600000000
        candle.close = 50000.0

        # Order that exceeds limit ($200,000)
        # 10 BTC at 50,000 = $500,000
        order = {"go": True, "side": "LONG", "qty": 10.0, "entry": 50000.0}

        events = broker.on_candle(candle, order)

        # Verify error is reported and no order submitted
        errors = events.get("errors", [])
        self.assertTrue(
            any("REJECTED: Order notional" in err for err in errors),
            f"Expected rejection error, got: {errors}",
        )
        provider.place_order.assert_not_called()

    def test_inverse_pnl_calculation(self):
        """Verify BTCUSDT Inverse PnL: PnL(BTC) = Notional * (1/Entry - 1/Exit)"""
        from laptop_agents.paper.broker import PaperBroker
        from dataclasses import dataclass

        @dataclass
        class MockCandle:
            ts: str = "2026-01-01T00:00:00Z"
            open: float = 90000.0
            high: float = 91000.0
            low: float = 89000.0
            close: float = 90500.0

        broker = PaperBroker(symbol="BTCUSDT")
        candle = MockCandle()

        # Simulate a LONG fill at market (90500)
        # Input qty is 0.005 BTC. Notional = 0.005 * 90500 = 452.5 USD.
        order = {
            "go": True,
            "side": "LONG",
            "entry_type": "market",
            "entry": 90500.0,
            "qty": 0.005,
            "sl": 89500.0,
            "tp": 92000.0,
            "equity": 10000.0,
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
        self.assertGreater(
            exit_event["pnl"],
            0,
            f"Expected positive PnL for profitable long, got {exit_event['pnl']}",
        )
        self.assertGreater(
            exit_event["r"], 0, f"Expected positive R-mult, got {exit_event['r']}"
        )
        print(
            f"Inverse PnL Test Passed: PnL={exit_event['pnl']:.8f} BTC, R={exit_event['r']:.2f}"
        )


if __name__ == "__main__":
    unittest.main()
