
import sys
import os
sys.path.append('src')
from laptop_agents.data.providers.bitunix_futures import BitunixFuturesProvider

def check_symbols():
    try:
        # Init with dummy symbol, it only asserts on allowed_symbols if provided
        provider = BitunixFuturesProvider(symbol="BTCUSDT") 
        pairs = provider.trading_pairs()
        print(f"Found {len(pairs)} trading pairs.")
        
        btc_pairs = [p.get("symbol") for p in pairs if "BTC" in p.get("symbol", "")]
        print("BTC Pairs:", btc_pairs)
        
    except Exception as e:
        print(f"Error checking symbols: {e}")

if __name__ == "__main__":
    check_symbols()
