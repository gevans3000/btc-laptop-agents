"""Utility to dump BTCUSDT instrument info from Bitunix."""
from laptop_agents.data.providers.bitunix_futures import BitunixFuturesProvider
import json

provider = BitunixFuturesProvider(symbol="BTCUSDT")
info = provider.fetch_instrument_info("BTCUSDT")
print("=== BTCUSDT Instrument Info ===")
print(json.dumps(info, indent=2))
print("\nKey fields to verify:")
print(f"  lotSize: {info.get('lotSize')} (Is this BTC or Contracts?)")
print(f"  tickSize: {info.get('tickSize')} (Price precision)")
