import unittest
from dataclasses import dataclass
from laptop_agents.paper.broker import PaperBroker
from laptop_agents.execution.bitunix_broker import BitunixBroker
from unittest.mock import MagicMock


@dataclass
class MockCandle:
    ts: str = "2026-01-01T00:00:00Z"
    close: float = 50000.0
    high: float = 51000.0
    low: float = 49000.0
    open: float = 50000.0


class TestDualModeMath(unittest.TestCase):
    """
    Verify that the system correctly handles math for BOTH:
    1. Linear (USDT-M): BTCUSDT
    2. Inverse (COIN-M): BTCUSDT
    """

    def test_linear_long_pnl(self):
        """BTCUSDT Long: PnL = (Exit - Entry) * Qty"""
        broker = PaperBroker(symbol="BTCUSDT", fees_bps=0, slip_bps=0)
        broker.exchange_fees = {"maker": 0, "taker": 0}
        self.assertFalse(broker.is_inverse, "BTCUSDT should NOT be inverse")

        # Entry at 50k, Qty 0.001 BTC
        order = {
            "go": True,
            "side": "LONG",
            "entry_type": "market",
            "entry": 50000.0,
            "qty": 0.001,
            "sl": 49000.0,
            "tp": 55000.0,
        }
        candle_entry = MockCandle(close=50000.0)
        broker.on_candle(candle_entry, order)

        # Exit at 52k
        # Check Unrealized PnL at 52k
        # Expected: (52000 - 50000) * 0.001 = 2000 * 0.001 = 2 USDT
        unrealized = broker.get_unrealized_pnl(52000.0)
        self.assertAlmostEqual(unrealized, 2.0, places=2)
        print("Linear LONG PnL Verified: +$2.00")

    def test_linear_short_pnl(self):
        """BTCUSDT Short: PnL = (Entry - Exit) * Qty"""
        broker = PaperBroker(symbol="BTCUSDT", fees_bps=0, slip_bps=0)
        broker.exchange_fees = {"maker": 0, "taker": 0}

        # Entry at 50k, Qty 0.001 BTC
        order = {
            "go": True,
            "side": "SHORT",
            "entry_type": "market",
            "entry": 50000.0,
            "qty": 0.001,
            "sl": 51000.0,
            "tp": 45000.0,
        }
        candle_entry = MockCandle(close=50000.0)
        broker.on_candle(candle_entry, order)

        # Exit at 48k (Profitable)
        # Expected: (50000 - 48000) * 0.001 = 2000 * 0.001 = 2 USDT
        unrealized = broker.get_unrealized_pnl(48000.0)
        self.assertAlmostEqual(unrealized, 2.0, places=2)
        print("Linear SHORT PnL Verified: +$2.00")

    def test_inverse_long_pnl(self):
        """BTCUSD Long: PnL(BTC) = NotionalUSD * (1/Entry - 1/Exit)"""
        broker = PaperBroker(symbol="BTCUSD", fees_bps=0, slip_bps=0)
        broker.exchange_fees = {"maker": 0, "taker": 0}
        self.assertTrue(broker.is_inverse, "BTCUSDT SHOULD be inverse")

        # Entry at 50k, 0.001 BTC -> Notional $50
        order = {
            "go": True,
            "side": "LONG",
            "entry_type": "market",
            "entry": 50000.0,
            "qty": 0.001,
            "sl": 49000.0,
            "tp": 55000.0,
        }
        candle_entry = MockCandle(close=50000.0)
        broker.on_candle(candle_entry, order)

        # Position Qty should be Notional ($50.0)
        self.assertEqual(broker.pos.qty, 50.0)

        # Exit at 100k (Doubled price) -> Should be ~0.0005 BTC profit?
        # PnL = 50 * (1/50000 - 1/100000) = 50 * (0.00001) = 0.0005 BTC.
        unrealized_btc = broker.get_unrealized_pnl(100000.0)
        self.assertAlmostEqual(unrealized_btc, 0.0005, places=6)
        print("Inverse LONG PnL Verified: +0.0005 BTC (at 2x price)")

    def test_inverse_short_pnl(self):
        """BTCUSD Short: PnL(BTC) = NotionalUSD * (1/Exit - 1/Entry)"""
        broker = PaperBroker(symbol="BTCUSD", fees_bps=0, slip_bps=0)
        broker.exchange_fees = {"maker": 0, "taker": 0}

        # Entry at 50k, 0.001 BTC (Notional $50)
        order = {
            "go": True,
            "side": "SHORT",
            "entry_type": "market",
            "entry": 50000.0,
            "qty": 0.001,
            "sl": 51000.0,
            "tp": 25000.0,
        }
        candle_entry = MockCandle(close=50000.0)
        broker.on_candle(candle_entry, order)

        # Exit at 25k (Halved price)
        # PnL = 50 * (1/25000 - 1/50000) = 50 * (0.00002) = 0.001 BTC.
        unrealized_btc = broker.get_unrealized_pnl(25000.0)
        self.assertAlmostEqual(unrealized_btc, 0.001, places=6)
        print("Inverse SHORT PnL Verified: +0.001 BTC (at 0.5x price)")


class TestBitunixDualMode(unittest.TestCase):
    """Verify BitunixBroker PnL logic mirrors PaperBroker"""

    def test_bitunix_linear_pnl(self):
        provider = MagicMock()
        provider.symbol = "BTCUSDT"
        broker = BitunixBroker(provider)
        self.assertFalse(broker.is_inverse)

        # Mock Long Position: Entry 50k, Qty 0.1
        broker.last_pos = {"qty": 0.1, "entryPrice": 50000.0, "side": "LONG"}

        # Current Price 52k -> PnL should be 200
        pnl = broker.get_unrealized_pnl(52000.0)
        self.assertAlmostEqual(pnl, 200.0, places=2)

    def test_bitunix_inverse_pnl(self):
        provider = MagicMock()
        provider.symbol = "BTCUSD"
        broker = BitunixBroker(provider)
        self.assertTrue(broker.is_inverse)

        # Scenario: Long 1 BTC at $50,000.
        # IF Bitunix returns Qty in BTC, then qty=1.0.
        # IF Bitunix returns Qty in USD, then qty=50000.0.
        # Based on 'lotSize: 0.001', we assume Qty is BTC.

        # Test Case A: Broker assumes inputs are USD (Current implementation behavior?)
        # Let's pass 1.0 (BTC) overlapping as "Qty".
        broker.last_pos = {"qty": 1.0, "entryPrice": 50000.0, "side": "LONG"}

        # Current Price 100k.
        # If formula is Qty * (1/Entry - 1/Exit) -> 1.0 * (1/50k - 1/100k) = 1 * (0.00001) = 0.00001 BTC.
        # But for 1 BTC Long ($50k notional), PnL should be 0.5 BTC.
        # So 0.00001 is WRONG by factor of 50,000 (Price).

        pnl = broker.get_unrealized_pnl(100000.0)

        # If the code is buggy, this will be 0.00001.
        # If the code handles BTC-denominated qty, it should be 0.5.
        print(f"DEBUG: Bitunix Inverse PnL Result for 1.0 BTC Input: {pnl}")

        # We Expect it to be 0.5 if logic is correct.
        # Changing assertion to fail if bug exists.
        if pnl < 0.1:
            print("CONFIRMED BUG: BitunixBroker treats BTC Qty as Contracts USD!")
        else:
            print("Pass: BitunixBroker correctly converts BTC Qty.")

        self.assertAlmostEqual(
            pnl,
            0.5,
            places=5,
            msg="PnL should be 0.5 BTC for 1 BTC Long doubling. Logic likely missing Qty->Notional conversion.",
        )


class TestBitunixExitPnL(unittest.TestCase):
    """Verify BitunixBroker calculates PnL on exit correctly"""

    def test_linear_exit_pnl(self):
        from dataclasses import dataclass

        @dataclass
        class FakeCandle:
            ts: str = "2026-01-01T00:00:00Z"
            close: float = 52000.0

        provider = MagicMock()
        provider.symbol = "BTCUSDT"
        provider.get_pending_positions = MagicMock(return_value=[])

        broker = BitunixBroker(provider)
        broker._initialized = True

        # Simulate a filled position
        broker._entry_price = 50000.0
        broker._entry_side = "LONG"
        broker._entry_qty = 0.1
        broker.last_pos = {"qty": 0.1, "entryPrice": 50000.0, "side": "LONG"}

        # Simulate exit (position gone, candle at 52k)
        events = broker.on_candle(FakeCandle(), None)

        self.assertEqual(len(events["exits"]), 1)
        exit_event = events["exits"][0]
        # Expected PnL: (52000 - 50000) * 0.1 = 200
        self.assertAlmostEqual(exit_event["pnl"], 200.0, places=2)
        print("Linear Exit PnL Test Passed: +$200")

    def test_inverse_exit_pnl(self):
        from dataclasses import dataclass

        @dataclass
        class FakeCandle:
            ts: str = "2026-01-01T00:00:00Z"
            close: float = 100000.0

        provider = MagicMock()
        provider.symbol = "BTCUSD"
        provider.get_pending_positions = MagicMock(return_value=[])

        broker = BitunixBroker(provider)
        broker._initialized = True

        # Simulate a filled position: 1 BTC Long at $50k
        broker._entry_price = 50000.0
        broker._entry_side = "LONG"
        broker._entry_qty = 1.0
        broker.last_pos = {"qty": 1.0, "entryPrice": 50000.0, "side": "LONG"}

        # Simulate exit at 100k
        events = broker.on_candle(FakeCandle(), None)

        self.assertEqual(len(events["exits"]), 1)
        exit_event = events["exits"][0]
        # Expected PnL: 50000 * (1/50000 - 1/100000) = 0.5 BTC
        self.assertAlmostEqual(exit_event["pnl"], 0.5, places=5)
        print("Inverse Exit PnL Test Passed: +0.5 BTC")


if __name__ == "__main__":
    unittest.main()
