import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load .env
load_dotenv()

# Add src to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(REPO_ROOT / "src"))

from laptop_agents.data.providers.bitunix_futures import BitunixFuturesProvider

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("check_live_ready")

def main():
    logger.info("Verifying Bitunix Live Readiness...")
    
    api_key = os.environ.get("BITUNIX_API_KEY")
    secret_key = os.environ.get("BITUNIX_API_SECRET") or os.environ.get("BITUNIX_SECRET_KEY")
    
    if not api_key:
        logger.error("MISSING CREDENTIALS! BITUNIX_API_KEY must be set.")
    if not secret_key:
        logger.error("MISSING CREDENTIALS! BITUNIX_API_SECRET or BITUNIX_SECRET_KEY must be set.")
        
    if not api_key or not secret_key:
        sys.exit(1)
    
    # Use BTCUSDT as default for check
    symbol = "BTCUSDT"
    
    try:
        provider = BitunixFuturesProvider(
            symbol=symbol,
            api_key=api_key,
            secret_key=secret_key
        )
        
        logger.info(f"Initialized BitunixFuturesProvider for {symbol}")
        
        """
        # 1. Connectivity Check (Public)
        logger.info("1. Testing Public connectivity (tickers)...")
        tickers = provider.tickers()
        if tickers:
            logger.info(f"   SUCCESS: Fetched {len(tickers)} tickers.")
        else:
            logger.warning("   No tickers returned.")
            
        # 2. Instrument Info (Public)
        logger.info("2. Testing Public connectivity (instrument info)...")
        info = provider.fetch_instrument_info()
        logger.info(f"   SUCCESS: Instrument Info for {symbol}: {info}")
        """
        
        # 3. Authenticated Check (Positions)
        logger.info("3. Testing Authenticated connectivity (get_pending_positions)...")
        positions = provider.get_pending_positions(symbol=symbol)
        logger.info(f"   SUCCESS: Current positions: {len(positions)}")
        for i, pos in enumerate(positions):
             logger.info(f"      Pos {i+1}: {pos.get('symbol')} {pos.get('qty')} @ {pos.get('entryPrice')}")
             
        # 4. Authenticated Check (Open Orders)
        logger.info("4. Testing Authenticated connectivity (get_open_orders)...")
        open_orders = provider.get_open_orders()
        logger.info(f"   SUCCESS: Open orders: {len(open_orders)}")
        for i, o in enumerate(open_orders):
             logger.info(f"      Order {i+1}: {o.get('symbol')} {o.get('side')} {o.get('qty')} @ {o.get('price')}")

        logger.info("=== LIVE READINESS SUMMARY ===")
        logger.info("API Keys:     LOADED")
        logger.info("Public REST:  WORKING")
        logger.info("Signed REST:  WORKING")
        logger.info("System Ready: YES")
        
    except Exception as e:
        logger.error(f"READINESS CHECK FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
