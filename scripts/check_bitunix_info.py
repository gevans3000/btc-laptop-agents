"""Utility to dump BTCUSD instrument info from Bitunix."""
from laptop_agents.data.providers.bitunix_futures import BitunixFuturesProvider
import json

provider = BitunixFuturesProvider(symbol="BTCUSD")
info = provider.fetch_instrument_info("BTCUSD")
print("=== BTCUSD Instrument Info ===")
print(json.dumps(info, indent=2))
print("\nKey fields to verify:")
print(f"  lotSize: {info.get('lotSize')} (Is this BTC or Contracts?)")
print(f"  tickSize: {info.get('tickSize')} (Price precision)")
