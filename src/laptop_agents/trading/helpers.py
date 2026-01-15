"""
Trading helpers extracted from run.py.
Phase 1 refactoring.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def calculate_fees(notional: float, fees_bps: float) -> float:
    """Helper function to calculate fees."""
    return notional * (fees_bps / 10_000.0)


def apply_slippage(price: float, is_entry: bool, is_long: bool, slip_bps: float) -> float:
    """Helper function to apply slippage."""
    slip_rate = slip_bps / 10_000.0
    if is_long:
        return price * (1.0 + slip_rate) if is_entry else price * (1.0 - slip_rate)
    else:
        return price * (1.0 - slip_rate) if is_entry else price * (1.0 + slip_rate)


@dataclass
class Candle:
    """OHLCV candle representation."""
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Tick:
    """Real-time market tick."""
    symbol: str
    bid: float
    ask: float
    last: float
    ts: str


def sma(vals: List[float], window: int) -> Optional[float]:
    """Simple moving average over the last `window` values."""
    if len(vals) < window:
        return None
    return sum(vals[-window:]) / float(window)


def normalize_candle_order(candles: List[Candle]) -> List[Candle]:
    """
    Ensure candles are in chronological order (oldest first, newest last).
    Detects and fixes newest-first ordering that some providers return.
    """
    if len(candles) < 2:
        return candles
    
    # Parse timestamps for comparison
    first_ts = candles[0].ts
    last_ts = candles[-1].ts
    
    # Try to detect order by comparing timestamps
    # If first > last, reverse the list
    try:
        if first_ts > last_ts:
            return list(reversed(candles))
    except Exception:
        pass
    
    return candles


def calculate_position_size(
    equity: float,
    entry_price: float,
    risk_pct: float,
    stop_bps: float,
    tp_r: float,
    max_leverage: float,
    is_long: bool = True,
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Calculate position size, stop price, and take-profit price.
    Returns (qty, stop_price, tp_price) or (None, None, None) if invalid.

    IMPORTANT: Returned `qty` is always in BASE COINS (e.g., BTC), not USD.
    For Inverse (Coin-M) futures, the broker will convert Coins to Notional USD internally.

    For LONG positions: stop < entry < tp
    For SHORT positions: tp < entry < stop
    """
    stop_distance = entry_price * (stop_bps / 10_000.0)
    if stop_distance <= 0:
        return None, None, None
    
    risk_amount = equity * (risk_pct / 100.0)
    qty_raw = risk_amount / stop_distance
    
    # Cap notional to max_leverage
    max_notional = equity * max_leverage
    max_qty = max_notional / entry_price if entry_price > 0 else 0.0
    qty = min(qty_raw, max_qty)
    
    if qty <= 0:
        return None, None, None
    
    # Calculate stop and tp prices based on direction
    if is_long:
        # LONG: stop below entry, tp above entry
        stop_price = entry_price - stop_distance
        tp_price = entry_price + (stop_distance * tp_r)
    else:
        # SHORT: tp below entry, stop above entry
        stop_price = entry_price + stop_distance
        tp_price = entry_price - (stop_distance * tp_r)
    
    # Add assertions to ensure correct ordering (only in backtest/validate modes)
    if is_long:
        if not (stop_price < entry_price < tp_price):
            raise ValueError(
                f"LONG position stop/tp ordering violation: "
                f"stop={stop_price:.2f}, entry={entry_price:.2f}, tp={tp_price:.2f}. "
                f"Expected: stop < entry < tp"
            )
    else:
        if not (tp_price < entry_price < stop_price):
            raise ValueError(
                f"SHORT position stop/tp ordering violation: "
                f"tp={tp_price:.2f}, entry={entry_price:.2f}, stop={stop_price:.2f}. "
                f"Expected: tp < entry < stop"
            )
    
    return qty, stop_price, tp_price


def utc_ts() -> str:
    """Get current UTC timestamp in ISO format with 'Z' suffix."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def simulate_trade_one_bar(
    *,
    signal: str,
    entry_px: float,
    exit_px: float,
    starting_balance: float,
    fees_bps: float,
    slip_bps: float,
) -> Dict[str, Any]:
    """
    One-trade, one-bar realized PnL:
      - entry at prev close
      - exit at last close
      - slippage applied adversely on both sides
      - fees charged on notional (entry + exit)
    """
    fees_rate = fees_bps / 10_000.0
    slip_rate = slip_bps / 10_000.0

    if signal == "BUY":
        side = "LONG"
        entry = entry_px * (1.0 + slip_rate)
        exit_ = exit_px * (1.0 - slip_rate)
        qty = starting_balance / entry if entry > 0 else 0.0
        gross = (exit_ - entry) * qty
    else:
        side = "SHORT"
        entry = entry_px * (1.0 - slip_rate)
        exit_ = exit_px * (1.0 + slip_rate)
        qty = starting_balance / entry if entry > 0 else 0.0
        gross = (entry - exit_) * qty

    fees = (entry * qty + exit_ * qty) * fees_rate
    pnl = gross - fees

    return {
        "trade_id": str(uuid.uuid4()),
        "side": side,
        "signal": signal,
        "entry": float(entry),
        "exit": float(exit_),
        "price": float(exit_),  # display as last/exit
        "quantity": float(qty),
        "pnl": float(pnl),
        "fees": float(fees),
        "timestamp": utc_ts(),
    }


def detect_candle_gaps(candles: List[Candle], interval: str = "1m") -> List[dict]:
    """Detect gaps in candle sequence."""
    if len(candles) < 2:
        return []
    
    interval_seconds = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}.get(interval, 60)
    gaps = []
    
    for i in range(1, len(candles)):
        try:
            prev_ts = int(candles[i-1].ts) if str(candles[i-1].ts).isdigit() else 0
            curr_ts = int(candles[i].ts) if str(candles[i].ts).isdigit() else 0
            if prev_ts > 0 and curr_ts > 0:
                expected_gap = interval_seconds
                actual_gap = curr_ts - prev_ts
                if actual_gap > expected_gap * 1.5:  # Allow 50% tolerance
                    missing = (actual_gap // interval_seconds) - 1
                    gaps.append({
                        "prev_ts": prev_ts,
                        "curr_ts": curr_ts,
                        "missing_count": int(missing)
                    })
        except (ValueError, TypeError):
            continue
    
    return gaps
