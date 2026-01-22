import unittest
from dataclasses import dataclass
from laptop_agents.paper.broker import PaperBroker


@dataclass
class MockCandle:
    ts: str
    open: float
    high: float
    low: float
    close: float


class TestTrailingStop(unittest.TestCase):
    def test_trailing_stop_long(self):
        """Verify that a LONG trailing stop moves up as price advances."""
        broker = PaperBroker(symbol="BTCUSDT", fees_bps=0, slip_bps=0)
        broker.exchange_fees = {"maker": 0, "taker": 0}

        # Entry at 50,000, SL at 48,000 (Risk = 2000).
        # Trail activates at +0.5R = 50,000 + 1000 = 51,000.
        # Trail distance = 1.5 ATR. Since we don't have ATR, but the logic uses abs(entry-sl),
        # the 'atr_mult' is applied to the initial stop distance.
        # Logic in broker.py: p.trail_stop = candle.close - abs(p.entry - p.sl) * 1.5
        # Trail distance = 2000 * 1.5 = 3000.

        order = {
            "go": True,
            "side": "LONG",
            "entry_type": "market",
            "entry": 50000.0,
            "qty": 0.005,
            "sl": 48000.0,
            "tp": 60000.0,
        }

        # 1. Entry
        c1 = MockCandle("T1", 50000, 50500, 49500, 50000)
        events = broker.on_candle(c1, order)
        print(f"Entry events: {events}")
        print(f"Broker position: {broker.pos}")
        self.assertFalse(broker.pos.trail_active)

        # 2. Advance to 51,001 (Should activate trail)
        # Activation: close > 50000 + 1000 = 51000
        c2 = MockCandle("T2", 50000, 51500, 50500, 51001)
        broker.on_candle(c2, None)
        self.assertTrue(broker.pos.trail_active)
        # trail_stop = 51001 - (2000 * 1.5) = 51001 - 3000 = 48001
        self.assertEqual(broker.pos.trail_stop, 48001)

        # 3. Advance to 55,000 (Should move trail up)
        c3 = MockCandle("T3", 51001, 55500, 54500, 55000)
        broker.on_candle(c3, None)
        # new_trail = 55000 - 3000 = 52000
        self.assertEqual(broker.pos.trail_stop, 52000)

        # 4. Price drops to 51,000 (Should HIT trail)
        c4 = MockCandle("T4", 55000, 55000, 51000, 51000)
        events = broker.on_candle(c4, None)
        self.assertEqual(len(events["exits"]), 1)
        self.assertEqual(events["exits"][0]["reason"], "TRAIL")
        self.assertEqual(events["exits"][0]["price"], 52000)
        print("Trailing Stop LONG Verified.")

    def test_trailing_stop_short(self):
        """Verify that a SHORT trailing stop moves down as price advances."""
        broker = PaperBroker(symbol="BTCUSDT", fees_bps=0, slip_bps=0)
        broker.exchange_fees = {"maker": 0, "taker": 0}

        # Entry at 50,000, SL at 52,000 (Risk = 2000).
        # Trail activates at +0.5R = 50,000 - 1000 = 49,000.
        # Trail distance = 2000 * 1.5 = 3000.

        order = {
            "go": True,
            "side": "SHORT",
            "entry_type": "market",
            "entry": 50000.0,
            "qty": 0.005,
            "sl": 52000.0,
            "tp": 40000.0,
        }

        # 1. Entry
        c1 = MockCandle("T1", 50000, 50500, 49500, 50000)
        broker.on_candle(c1, order)

        # 2. Advance to 48,999 (Should activate trail)
        c2 = MockCandle("T2", 50000, 49500, 48500, 48999)
        broker.on_candle(c2, None)
        self.assertTrue(broker.pos.trail_active)
        # trail_stop = 48999 + 3000 = 51999
        self.assertEqual(broker.pos.trail_stop, 51999)

        # 3. Advance to 45,000 (Should move trail down)
        c3 = MockCandle("T3", 48999, 45500, 44500, 45000)
        broker.on_candle(c3, None)
        # new_trail = 45000 + 3000 = 48000
        self.assertEqual(broker.pos.trail_stop, 48000)

        # 4. Price rises to 49,000 (Should HIT trail)
        c4 = MockCandle("T4", 45000, 49000, 45000, 49000)
        events = broker.on_candle(c4, None)
        self.assertEqual(len(events["exits"]), 1)
        self.assertEqual(events["exits"][0]["reason"], "TRAIL")
        self.assertEqual(events["exits"][0]["price"], 48000)
        print("Trailing Stop SHORT Verified.")


if __name__ == "__main__":
    unittest.main()
