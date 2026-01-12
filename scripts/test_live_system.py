"""
Test script for Live Trading System updates.
Tests:
1. BitunixFuturesProvider new methods (get_open_orders, cancel_all_orders)
2. BitunixBroker fixed $10 sizing logic
3. BitunixBroker shutdown() method
"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Setup paths
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

print("=" * 60)
print("LIVE TRADING SYSTEM TEST SUITE")
print("=" * 60)

# ============================================================
# TEST 1: Provider Methods Exist
# ============================================================
print("\n[TEST 1] Checking BitunixFuturesProvider has new methods...")

from laptop_agents.data.providers.bitunix_futures import BitunixFuturesProvider

provider_methods = ['get_open_orders', 'cancel_order', 'cancel_all_orders', 'get_pending_positions', 'place_order']
missing = [m for m in provider_methods if not hasattr(BitunixFuturesProvider, m)]

if missing:
    print(f"   FAIL: Missing methods: {missing}")
    sys.exit(1)
else:
    print(f"   PASS: All required methods present: {provider_methods}")

# ============================================================
# TEST 2: BitunixBroker Fixed $10 Sizing Logic (Unit Test)
# ============================================================
print("\n[TEST 2] Testing BitunixBroker $10 fixed sizing logic...")

from laptop_agents.execution.bitunix_broker import BitunixBroker

# Create a mock provider
mock_provider = MagicMock(spec=BitunixFuturesProvider)
mock_provider.symbol = "BTCUSD"
mock_provider.fetch_instrument_info.return_value = {
    "tickSize": 0.01,
    "lotSize": 0.001,
    "minQty": 0.001,
    "maxQty": 1000.0
}
mock_provider.get_pending_positions.return_value = []
mock_provider.place_order.return_value = {"code": 0, "data": {"orderId": "test123"}, "msg": "Success"}

broker = BitunixBroker(mock_provider)

# Create a mock candle
class MockCandle:
    def __init__(self, close):
        self.close = close
        self.ts = "2026-01-12T00:00:00Z"

# Test scenario: Price = $100,000, expected qty = 10 / 100000 = 0.0001
# But minQty is 0.001, so it should be bumped up to 0.001
candle = MockCandle(close=100000.0)

# Create order that would trigger a buy
order = {
    "go": True,
    "side": "LONG",
    "entry": 100000.0,
    "qty": 999.0,  # This should be IGNORED and replaced with $10 / price
    "sl": 99000.0,
    "tp": 101000.0,
    "equity": 10000.0
}

# Patch input to auto-confirm and os.environ to skip confirmation
with patch.dict(os.environ, {"SKIP_LIVE_CONFIRM": "TRUE"}):
    with patch('os.path.exists', return_value=False):  # No kill switch file
        events = broker.on_candle(candle, order)

# Check that place_order was called
if mock_provider.place_order.called:
    call_args = mock_provider.place_order.call_args
    actual_qty = call_args.kwargs.get('qty')
    
    # Expected: 10.0 / 100000.0 = 0.0001, but minQty is 0.001
    # So it should be 0.001
    expected_qty = 0.001
    
    if abs(actual_qty - expected_qty) < 0.0001:
        print(f"   PASS: Fixed sizing works. Qty = {actual_qty} (expected {expected_qty})")
    else:
        print(f"   FAIL: Wrong qty. Got {actual_qty}, expected {expected_qty}")
        sys.exit(1)
else:
    print("   FAIL: place_order was not called")
    sys.exit(1)

# ============================================================
# TEST 3: BitunixBroker shutdown() method exists and works
# ============================================================
print("\n[TEST 3] Testing BitunixBroker shutdown() method...")

mock_provider2 = MagicMock(spec=BitunixFuturesProvider)
mock_provider2.symbol = "BTCUSD"
mock_provider2.cancel_all_orders.return_value = {"code": 0, "data": {"successList": [], "failureList": []}, "msg": "Success"}
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
secret_key = os.environ.get("BITUNIX_API_SECRET") or os.environ.get("BITUNIX_SECRET_KEY")

if not api_key or not secret_key:
    print("   SKIP: No API credentials found in environment")
else:
    try:
        live_provider = BitunixFuturesProvider(
            symbol="BTCUSD",
            api_key=api_key,
            secret_key=secret_key
        )
        
        # Test get_pending_positions
        positions = live_provider.get_pending_positions(symbol="BTCUSD")
        print(f"   PASS: get_pending_positions() returned {len(positions)} positions")
        
        # Test get_open_orders
        orders = live_provider.get_open_orders()
        print(f"   PASS: get_open_orders() returned {len(orders)} orders")
        
        # Test cancel_all_orders (safe - just cancels any open orders)
        result = live_provider.cancel_all_orders(symbol="BTCUSD")
        print(f"   PASS: cancel_all_orders() succeeded: {result.get('msg')}")
        
    except Exception as e:
        print(f"   FAIL: Live API test failed: {e}")
        sys.exit(1)

# ============================================================
# TEST 5: timed_session supports execution_mode parameter
# ============================================================
print("\n[TEST 5] Testing timed_session execution_mode parameter...")

import inspect
from laptop_agents.session.timed_session import run_timed_session

sig = inspect.signature(run_timed_session)
if 'execution_mode' in sig.parameters:
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
print("  $env:PYTHONPATH='src'; python src/laptop_agents/run.py --mode live-session --source bitunix --symbol BTCUSD --execution-mode paper --duration 2")
