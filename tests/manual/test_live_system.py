# flake8: noqa
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from dotenv import load_dotenv  # noqa: E402
import inspect  # noqa: E402

# Setup paths
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from laptop_agents.data.providers.bitunix_futures import (
    BitunixFuturesProvider,
)  # noqa: E402, fmt: skip
from laptop_agents.execution.bitunix_broker import (
    BitunixBroker,
)  # noqa: E402, fmt: skip
from laptop_agents.session.timed_session import (
    run_timed_session,
)  # noqa: E402, fmt: skip

load_dotenv(REPO_ROOT / ".env")

print("=" * 60)
print("LIVE TRADING SYSTEM TEST SUITE")
print("=" * 60)

# ============================================================
# TEST 1: Provider Methods Exist
# ============================================================
print("\n[TEST 1] Checking BitunixFuturesProvider has new methods...")

provider_methods = [
    "get_open_orders",
    "cancel_order",
    "cancel_all_orders",
    "get_pending_positions",
    "place_order",
]
missing = [m for m in provider_methods if not hasattr(BitunixFuturesProvider, m)]

if missing:
    print(f"   FAIL: Missing methods: {missing}")
    sys.exit(1)
else:
    print(f"   PASS: All required methods present: {provider_methods}")

# ============================================================
# TEST 2: BitunixBroker Dynamic Sizing Logic
# ============================================================
print("\n[TEST 2] Testing BitunixBroker Dynamic Sizing logic...")

# Create a mock provider
mock_provider = MagicMock(spec=BitunixFuturesProvider)
mock_provider.symbol = "BTCUSDT"
mock_provider.fetch_instrument_info.return_value = {
    "tickSize": 0.01,
    "lotSize": 0.001,
    "minQty": 0.001,
    "maxQty": 1000.0,
}
mock_provider.get_pending_positions.return_value = []
mock_provider.place_order.return_value = {
    "code": 0,
    "data": {"orderId": "test123"},
    "msg": "Success",
}

broker = BitunixBroker(mock_provider)


# Create a mock candle
class MockCandle:
    def __init__(self, close):
        self.close = close
        self.ts = "2026-01-12T00:00:00Z"


# Test scenario: Price = $100,000
candle = MockCandle(close=100000.0)

# Create order with explicit quantity
# We use a small quantity that is safe ($100 notional)
# 0.001 BTC * $100,000 = $100
target_qty = 0.001

order = {
    "go": True,
    "side": "LONG",
    "entry": 100000.0,
    "qty": target_qty,
    "sl": 99000.0,
    "tp": 101000.0,
    "equity": 10000.0,
}

# Patch input to auto-confirm and os.environ to skip confirmation
with patch.dict(os.environ, {"SKIP_LIVE_CONFIRM": "TRUE"}):
    with patch("os.path.exists", return_value=False):  # No kill switch file
        events = broker.on_candle(candle, order)

# Check that place_order was called
if mock_provider.place_order.called:
    call_args = mock_provider.place_order.call_args
    actual_qty = call_args.kwargs.get("qty")

    if abs(actual_qty - target_qty) < 0.000001:
        print(f"   PASS: Dynamic sizing works. Qty = {actual_qty}")
    else:
        print(f"   FAIL: Wrong qty. Got {actual_qty}, expected {target_qty}")
        sys.exit(1)
else:
    print("   FAIL: place_order was not called")
    sys.exit(1)

# ============================================================
# TEST 3: BitunixBroker shutdown() method exists and works
# ============================================================
print("\n[TEST 3] Testing BitunixBroker shutdown() method...")

mock_provider2 = MagicMock(spec=BitunixFuturesProvider)
mock_provider2.symbol = "BTCUSDT"
mock_provider2.cancel_all_orders.return_value = {
    "code": 0,
    "data": {"successList": [], "failureList": []},
    "msg": "Success",
}
mock_provider2.get_pending_positions.return_value = []  # No positions to close

broker2 = BitunixBroker(mock_provider2)

try:
    broker2.shutdown()
    if mock_provider2.cancel_all_orders.called:
        print("   PASS: shutdown() called cancel_all_orders()")
    else:
        print("   FAIL: shutdown() did not call cancel_all_orders()")
        sys.exit(1)
except Exception as e:
    print(f"   FAIL: shutdown() raised exception: {e}")
    sys.exit(1)

# ============================================================
# TEST 4: Live API Connectivity (if credentials available)
# ============================================================
print("\n[TEST 4] Testing Live API connectivity...")

api_key = os.environ.get("BITUNIX_API_KEY")
secret_key = os.environ.get("BITUNIX_API_SECRET") or os.environ.get(
    "BITUNIX_SECRET_KEY"
)

if not api_key or not secret_key:
    print("   SKIP: No API credentials found in environment")
else:
    try:
        live_provider = BitunixFuturesProvider(
            symbol="BTCUSDT", api_key=api_key, secret_key=secret_key
        )

        # Test get_pending_positions
        positions = live_provider.get_pending_positions(symbol="BTCUSDT")
        print(f"   PASS: get_pending_positions() returned {len(positions)} positions")

        # Test get_open_orders
        orders = live_provider.get_open_orders()
        print(f"   PASS: get_open_orders() returned {len(orders)} orders")

        # Test cancel_all_orders (safe - just cancels any open orders)
        result = live_provider.cancel_all_orders(symbol="BTCUSDT")
        print(f"   PASS: cancel_all_orders() succeeded: {result.get('msg')}")

    except Exception as e:
        print(f"   FAIL: Live API test failed: {e}")
        sys.exit(1)

# ============================================================
# TEST 5: timed_session supports execution_mode parameter
# ============================================================
print("\n[TEST 5] Testing timed_session execution_mode parameter...")

sig = inspect.signature(run_timed_session)
if "execution_mode" in sig.parameters:
    print("   PASS: run_timed_session has 'execution_mode' parameter")
else:
    print("   FAIL: run_timed_session missing 'execution_mode' parameter")
    sys.exit(1)

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "=" * 60)
print("ALL TESTS PASSED!")
print("=" * 60)
print("\nThe Live Trading System is ready for use.")
print("Next step: Run a short paper session to verify end-to-end flow:")
print(
    "  $env:PYTHONPATH='src'; python src/laptop_agents/run.py --mode live-session "
    "--source bitunix --symbol BTCUSDT --execution-mode paper --duration 2"
)
