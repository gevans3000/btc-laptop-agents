import unittest
from laptop_agents.paper.broker import PaperBroker, Position


class TestTrailingStop(unittest.TestCase):
    def test_trail_activates_on_profit(self):
        broker = PaperBroker(symbol="BTCUSDT")
        # Simulate position entry
        from collections import deque

        broker.pos = Position(
            side="LONG",
            qty=0.1,
            sl=49000,
            tp=52000,
            opened_at="2026-01-01T00:00:00Z",
            lots=deque([{"qty": 0.1, "price": 50000, "fees": 0.0}]),
        )

        # Price moves up 1% (>0.5R) - should activate trail
        class FakeCandle:
            ts = "2026-01-01T00:01:00Z"
            open = high = close = 50600  # +1.2% profit
            low = 50500

        broker._check_exit(FakeCandle())
        self.assertTrue(broker.pos.trail_active)
        self.assertGreater(broker.pos.trail_stop, 0)

    def test_trail_stop_moves_up(self):
        broker = PaperBroker(symbol="BTCUSDT")
        from collections import deque

        broker.pos = Position(
            side="LONG",
            qty=0.1,
            sl=49000,
            tp=52000,
            opened_at="2026-01-01T00:00:00Z",
            lots=deque([{"qty": 0.1, "price": 50000, "fees": 0.0}]),
        )
        broker.pos.trail_active = True
        broker.pos.trail_stop = 50000

        class FakeCandle:
            ts = "2026-01-01T00:02:00Z"
            open = high = close = 52000
            low = 51900

        broker._check_exit(FakeCandle())
        self.assertGreater(broker.pos.trail_stop, 50000)


if __name__ == "__main__":
    unittest.main()
