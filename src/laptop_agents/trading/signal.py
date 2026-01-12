from __future__ import annotations
from typing import List, Optional
from laptop_agents.trading.helpers import Candle, sma
from laptop_agents.indicators import atr

def generate_signal(candles: List[Candle], fast_period: int = 10, slow_period: int = 30) -> Optional[str]:
    """
    Generate BUY/SELL signal based on SMA crossover.
    Includes ATR-based volatility filter:
    If ATR(14) / Close < 0.005, return None (Low Volatility).
    """
    if not candles or len(candles) < max(fast_period, slow_period):
        return None
        
    closes = [float(c.close) for c in candles]
    fast_sma = sma(closes, fast_period)
    slow_sma = sma(closes, slow_period)
    
    if fast_sma is None or slow_sma is None:
        return None
        
    # ATR Volatility Filter
    current_close = closes[-1]
    # We need at least period + 1 for ATR, which is 15 for ATR(14)
    # Candle count is already checked by slow_period (30) > 15
    a = atr(candles, 14)
    
    if a is not None:
        volatility_ratio = a / current_close
        if volatility_ratio < 0.005:
            # Low Volatility - HOLD
            return None
            
    if fast_sma > slow_sma:
        return "BUY"
    else:
        return "SELL"
