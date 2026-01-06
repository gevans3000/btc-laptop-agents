from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------- Paths (anchor to repo root) ----------------
HERE = Path(__file__).resolve()
repo = HERE
for _ in range(10):
    if (repo / "pyproject.toml").exists():
        break
    repo = repo.parent
RUNS_DIR = repo / "runs"
LATEST_DIR = RUNS_DIR / "latest"
PAPER_DIR = repo / "paper"


def utc_ts() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def reset_latest_dir() -> None:
    RUNS_DIR.mkdir(exist_ok=True)
    if LATEST_DIR.exists():
        shutil.rmtree(LATEST_DIR)
    LATEST_DIR.mkdir(parents=True, exist_ok=True)


def append_event(obj: Dict[str, Any], paper: bool = False) -> None:
    obj.setdefault("timestamp", utc_ts())
    if paper:
        PAPER_DIR.mkdir(exist_ok=True)
        with (PAPER_DIR / "events.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    else:
        with (LATEST_DIR / "events.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


@dataclass
class Candle:
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float


def load_mock_candles(n: int = 200) -> List[Candle]:
    candles: List[Candle] = []
    price = 100_000.0
    for i in range(n):
        price += 5.0 + (20.0 if (i % 20) < 10 else -20.0)
        o = price - 10.0
        c = price + 10.0
        h = max(o, c) + 15.0
        l = min(o, c) - 15.0
        candles.append(Candle(ts=f"mock_{i:04d}", open=o, high=h, low=l, close=c, volume=1.0))
    return candles


def _get_bitunix_provider_class():
    import laptop_agents.data.providers.bitunix_futures as m
    for name in dir(m):
        obj = getattr(m, name)
        if isinstance(obj, type) and hasattr(obj, "klines"):
            return obj
    raise RuntimeError("No Bitunix provider class with .klines() found in laptop_agents.data.providers.bitunix_futures")


def load_bitunix_candles(symbol: str, interval: str, limit: int) -> List[Candle]:
    Provider = _get_bitunix_provider_class()
    client = Provider(symbol=symbol)
    rows = client.klines(interval=interval, limit=int(limit))

    out: List[Candle] = []
    for c in rows:
        ts = getattr(c, "ts", None) or getattr(c, "time", None) or getattr(c, "timestamp", None) or ""
        o = float(getattr(c, "open"))
        h = float(getattr(c, "high"))
        l = float(getattr(c, "low"))
        cl = float(getattr(c, "close"))
        v = float(getattr(c, "volume", 0.0) or 0.0)
        out.append(Candle(ts=str(ts), open=o, high=h, low=l, close=cl, volume=v))
    return out


def sma(vals: List[float], window: int) -> Optional[float]:
    if len(vals) < window:
        return None
    return sum(vals[-window:]) / float(window)


def calculate_position_size(
    equity: float,
    entry_price: float,
    risk_pct: float,
    stop_bps: float,
    tp_r: float,
    max_leverage: float,
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Calculate position size, stop price, and take-profit price.
    Returns (qty, stop_price, tp_price) or (None, None, None) if invalid.
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
    
    # Calculate stop and tp prices
    stop_price = entry_price - stop_distance
    tp_price = entry_price + (stop_distance * tp_r)
    
    return qty, stop_price, tp_price


def normalize_candle_order(candles: List[Candle]) -> List[Candle]:
    """
    Ensure candles are in chronological order (oldest first, newest last).
    Detects and fixes newest-first ordering that some providers return.
    """
    if len(candles) < 2:
        return candles
    
    # Try to detect ordering by comparing first and last timestamps
    # If we can parse timestamps as datetime, use that for comparison
    try:
        # For mock data or ISO timestamps
        if "mock_" in candles[0].ts or "T" in candles[0].ts or ":" in candles[0].ts:
            # Assume chronological if first timestamp is "earlier" than last
            is_newest_first = candles[0].ts > candles[-1].ts
        else:
            # For numeric timestamps, compare as floats
            is_newest_first = float(candles[0].ts) > float(candles[-1].ts)
    except (ValueError, AttributeError):
        # If we can't determine, assume they're in correct order
        is_newest_first = False
    
    if is_newest_first:
        reversed_candles = list(reversed(candles))
        append_event({"event": "CandlesReversed", "original_count": len(candles),
                     "first_ts": candles[0].ts, "last_ts": candles[-1].ts})
        return reversed_candles
    
    return candles


def run_backtest_bar_mode(candles: List[Candle], starting_balance: float, fees_bps: float, slip_bps: float) -> Dict[str, Any]:
    """
    Run backtest in bar mode (original behavior).
    Uses SMA(10) vs SMA(30) with no lookahead, one trade per bar.
    """
    if len(candles) < 31:  # Need at least 30 for SMA(30) + 1 for trading
        raise ValueError(f"Need at least 31 candles for backtest, got {len(candles)}")
    
    # Normalize candle order first
    candles = normalize_candle_order(candles)
    
    # Backtest parameters
    fast_window = 10
    slow_window = 30
    warmup = max(fast_window, slow_window)
    
    # Initialize
    equity = starting_balance
    equity_history = []
    trades = []
    
    # Track stats
    wins = 0
    losses = 0
    total_fees = 0.0
    max_equity = starting_balance
    max_drawdown = 0.0
    
    # Pre-compute all closes for SMA calculations
    closes = [float(c.close) for c in candles]
    
    # Backtest loop - start after warmup period
    for i in range(warmup, len(candles)):
        # Compute SMAs on history up to i-1 (no lookahead)
        fast_sma = sma(closes[:i], fast_window)
        slow_sma = sma(closes[:i], slow_window)
        
        if fast_sma is None or slow_sma is None:
            # Not enough data yet, skip
            continue
        
        # Generate signal
        signal = "BUY" if fast_sma > slow_sma else "SELL"
        
        # Simulate trade: entry at close[i-1], exit at close[i]
        entry_px = float(candles[i-1].close)
        exit_px = float(candles[i].close)
        
        trade = simulate_trade_one_bar(
            signal=signal,
            entry_px=entry_px,
            exit_px=exit_px,
            starting_balance=equity,  # Use current equity, not starting balance
            fees_bps=fees_bps,
            slip_bps=slip_bps,
        )
        
        # Update equity and stats
        equity += float(trade["pnl"])
        total_fees += float(trade["fees"])
        
        # Track max drawdown
        max_equity = max(max_equity, equity)
        current_drawdown = (max_equity - equity) / max_equity if max_equity > 0 else 0
        max_drawdown = max(max_drawdown, current_drawdown)
        
        # Count wins/losses
        if float(trade["pnl"]) >= 0:
            wins += 1
        else:
            losses += 1
        
        trades.append(trade)
        
        # Record equity at this step (use candle timestamp)
        equity_history.append({
            "ts": candles[i].ts,
            "equity": float(equity)
        })
    
    # Write equity.csv
    equity_csv_path = LATEST_DIR / "equity.csv"
    temp_equity = equity_csv_path.with_suffix(".tmp")
    try:
        with temp_equity.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["ts", "equity"])
            writer.writeheader()
            for eq in equity_history:
                writer.writerow(eq)
        temp_equity.replace(equity_csv_path)
    except Exception as e:
        if temp_equity.exists():
            temp_equity.unlink()
        raise RuntimeError(f"Failed to write equity.csv: {e}")
    
    # Calculate stats
    win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0.0
    net_pnl = equity - starting_balance
    
    stats = {
        "trades": len(trades),
        "wins": wins,
        "losses": losses,
        "win_rate": float(win_rate),
        "net_pnl": float(net_pnl),
        "fees_total": float(total_fees),
        "max_drawdown": float(max_drawdown),
        "starting_balance": float(starting_balance),
        "ending_balance": float(equity),
    }
    
    # Write stats.json
    stats_path = LATEST_DIR / "stats.json"
    temp_stats = stats_path.with_suffix(".tmp")
    try:
        with temp_stats.open("w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2)
        temp_stats.replace(stats_path)
    except Exception as e:
        if temp_stats.exists():
            temp_stats.unlink()
        raise RuntimeError(f"Failed to write stats.json: {e}")
    
    return {
        "trades": trades,
        "equity_history": equity_history,
        "stats": stats,
        "ending_balance": equity
    }


def run_backtest_position_mode(
    candles: List[Candle],
    starting_balance: float,
    fees_bps: float,
    slip_bps: float,
    risk_pct: float = 1.0,
    stop_bps: float = 30.0,
    tp_r: float = 1.5,
    max_leverage: float = 1.0,
    intrabar_mode: str = "conservative",
) -> Dict[str, Any]:
    """
    Run backtest in position mode with risk-based sizing and stop/take-profit.
    """
    if len(candles) < 31:  # Need at least 30 for SMA(30) + 1 for trading
        raise ValueError(f"Need at least 31 candles for backtest, got {len(candles)}")

    # Normalize candle order first
    candles = normalize_candle_order(candles)

    # Backtest parameters
    fast_window = 10
    slow_window = 30
    warmup = max(fast_window, slow_window)

    # Initialize
    equity = starting_balance
    realized_equity = starting_balance  # Track realized PnL only
    equity_history = []
    trades = []

    # Position tracking
    position = None  # None, "LONG", or "SHORT"
    entry_price = 0.0
    entry_ts = ""
    position_quantity = 0.0
    stop_price = 0.0
    tp_price = 0.0

    # Track stats
    wins = 0
    losses = 0
    total_fees = 0.0
    max_equity = starting_balance
    max_drawdown = 0.0
    total_pnl = 0.0

    # Pre-compute all closes for SMA calculations
    closes = [float(c.close) for c in candles]

    # Helper function to calculate fees
    def calculate_fees(notional: float) -> float:
        return notional * (fees_bps / 10_000.0)

    # Helper function to apply slippage
    def apply_slippage(price: float, is_entry: bool, is_long: bool) -> float:
        slip_rate = slip_bps / 10_000.0
        if is_long:
            return price * (1.0 + slip_rate) if is_entry else price * (1.0 - slip_rate)
        else:
            return price * (1.0 - slip_rate) if is_entry else price * (1.0 + slip_rate)

    # Backtest loop - start after warmup period
    for i in range(warmup, len(candles)):
        current_candle = candles[i]
        current_close = float(current_candle.close)
        current_high = float(current_candle.high)
        current_low = float(current_candle.low)
        
        # Compute SMAs on history up to current index (no lookahead)
        fast_sma = sma(closes[:i+1], fast_window)  # Include current candle
        slow_sma = sma(closes[:i+1], slow_window)
        
        if fast_sma is None or slow_sma is None:
            # Not enough data yet, skip
            continue
        
        # Generate signal
        signal = "BUY" if fast_sma > slow_sma else "SELL"
        
        # Mark-to-market: calculate unrealized PnL if we have a position
        if position is not None:
            if position == "LONG":
                unrealized_pnl = (current_close - entry_price) * position_quantity
            else:  # SHORT
                unrealized_pnl = (entry_price - current_close) * position_quantity
            m2m_equity = realized_equity + unrealized_pnl
        else:
            m2m_equity = realized_equity
        
        # Position management logic
        if position is None:
            # No position open, look to enter
            if signal == "BUY":
                # Calculate position size with risk management
                qty, stop_price, tp_price = calculate_position_size(
                    equity=m2m_equity,
                    entry_price=current_close,
                    risk_pct=risk_pct,
                    stop_bps=stop_bps,
                    tp_r=tp_r,
                    max_leverage=max_leverage,
                )
                
                if qty is None:
                    append_event({"event": "RiskSizingSkipped", "reason": "invalid stop distance or qty"})
                    continue
                
                # Apply slippage to entry price
                entry_price_slipped = apply_slippage(current_close, True, True)
                entry_fees = calculate_fees(entry_price_slipped * qty)
                
                position = "LONG"
                entry_price = entry_price_slipped
                entry_ts = current_candle.ts
                position_quantity = qty
                realized_equity -= entry_fees
                total_fees += entry_fees
                
                append_event({"event": "PositionOpened", "side": "LONG", "ts": current_candle.ts,
                             "price": entry_price, "quantity": qty, "stop": stop_price, "tp": tp_price})
            elif signal == "SELL":
                # Calculate position size with risk management
                qty, stop_price, tp_price = calculate_position_size(
                    equity=m2m_equity,
                    entry_price=current_close,
                    risk_pct=risk_pct,
                    stop_bps=stop_bps,
                    tp_r=tp_r,
                    max_leverage=max_leverage,
                )
                
                if qty is None:
                    append_event({"event": "RiskSizingSkipped", "reason": "invalid stop distance or qty"})
                    continue
                
                # Apply slippage to entry price
                entry_price_slipped = apply_slippage(current_close, True, False)
                entry_fees = calculate_fees(entry_price_slipped * qty)
                
                position = "SHORT"
                entry_price = entry_price_slipped
                entry_ts = current_candle.ts
                position_quantity = qty
                realized_equity -= entry_fees
                total_fees += entry_fees
                
                append_event({"event": "PositionOpened", "side": "SHORT", "ts": current_candle.ts,
                             "price": entry_price, "quantity": qty, "stop": stop_price, "tp": tp_price})
        else:
            # Position is open, check for stop/tp hits
            exit_reason = None
            exit_price = None
            
            if position == "LONG":
                # Check if stop or tp was hit
                stop_hit = current_low <= stop_price
                tp_hit = current_high >= tp_price
                
                if stop_hit and tp_hit:
                    # Both hit in same candle - use intrabar mode
                    if intrabar_mode == "conservative":
                        exit_reason = "STOP"
                        exit_price = stop_price
                    else:
                        exit_reason = "TP"
                        exit_price = tp_price
                elif stop_hit:
                    exit_reason = "STOP"
                    exit_price = stop_price
                elif tp_hit:
                    exit_reason = "TP"
                    exit_price = tp_price
            else:  # SHORT
                # Check if stop or tp was hit
                stop_hit = current_high >= stop_price
                tp_hit = current_low <= tp_price
                
                if stop_hit and tp_hit:
                    # Both hit in same candle - use intrabar mode
                    if intrabar_mode == "conservative":
                        exit_reason = "STOP"
                        exit_price = stop_price
                    else:
                        exit_reason = "TP"
                        exit_price = tp_price
                elif stop_hit:
                    exit_reason = "STOP"
                    exit_price = stop_price
                elif tp_hit:
                    exit_reason = "TP"
                    exit_price = tp_price
            
            # If exit triggered, close position
            if exit_reason is not None:
                # Apply slippage to exit price
                exit_price_slipped = apply_slippage(exit_price, False, position == "LONG")
                
                if position == "LONG":
                    pnl = (exit_price_slipped - entry_price) * position_quantity
                else:
                    pnl = (entry_price - exit_price_slipped) * position_quantity
                
                exit_fees = calculate_fees(exit_price_slipped * position_quantity)
                
                # Create trade record
                trade = {
                    "trade_id": str(uuid.uuid4()),
                    "side": position,
                    "signal": "BUY" if position == "LONG" else "SELL",
                    "entry": float(entry_price),
                    "exit": float(exit_price_slipped),
                    "price": float(exit_price_slipped),
                    "quantity": float(position_quantity),
                    "pnl": float(pnl - exit_fees),
                    "fees": float(exit_fees),
                    "entry_ts": entry_ts,
                    "exit_ts": current_candle.ts,
                    "timestamp": utc_ts(),
                    "exit_reason": exit_reason,
                    "stop_price": float(stop_price),
                    "tp_price": float(tp_price),
                }
                trades.append(trade)
                
                # Update stats
                total_pnl += pnl - exit_fees
                if pnl - exit_fees >= 0:
                    wins += 1
                else:
                    losses += 1
                
                # Clear position
                realized_equity += pnl - exit_fees
                total_fees += exit_fees
                position = None
                
                append_event({"event": "PositionClosed", "side": position, "ts": current_candle.ts,
                             "price": exit_price_slipped, "pnl": pnl - exit_fees, "reason": exit_reason})
            elif (position == "LONG" and signal == "SELL") or (position == "SHORT" and signal == "BUY"):
                # Crossover reversal - close at current close
                exit_price_slipped = apply_slippage(current_close, False, position == "LONG")
                
                if position == "LONG":
                    pnl = (exit_price_slipped - entry_price) * position_quantity
                else:
                    pnl = (entry_price - exit_price_slipped) * position_quantity
                
                exit_fees = calculate_fees(exit_price_slipped * position_quantity)
                
                # Create trade record
                trade = {
                    "trade_id": str(uuid.uuid4()),
                    "side": position,
                    "signal": "BUY" if position == "LONG" else "SELL",
                    "entry": float(entry_price),
                    "exit": float(exit_price_slipped),
                    "price": float(exit_price_slipped),
                    "quantity": float(position_quantity),
                    "pnl": float(pnl - exit_fees),
                    "fees": float(exit_fees),
                    "entry_ts": entry_ts,
                    "exit_ts": current_candle.ts,
                    "timestamp": utc_ts(),
                    "exit_reason": "REVERSE",
                    "stop_price": float(stop_price),
                    "tp_price": float(tp_price),
                }
                trades.append(trade)
                
                # Update stats
                total_pnl += pnl - exit_fees
                if pnl - exit_fees >= 0:
                    wins += 1
                else:
                    losses += 1
                
                # Clear position
                realized_equity += pnl - exit_fees
                total_fees += exit_fees
                position = None
                
                append_event({"event": "PositionClosed", "side": position, "ts": current_candle.ts,
                             "price": exit_price_slipped, "pnl": pnl - exit_fees, "reason": "REVERSE"})
                
                # Open opposite position
                if signal == "BUY":
                    # Calculate position size with risk management
                    qty, stop_price, tp_price = calculate_position_size(
                        equity=realized_equity,
                        entry_price=current_close,
                        risk_pct=risk_pct,
                        stop_bps=stop_bps,
                        tp_r=tp_r,
                        max_leverage=max_leverage,
                    )
                    
                    if qty is None:
                        append_event({"event": "RiskSizingSkipped", "reason": "invalid stop distance or qty"})
                        continue
                    
                    # Apply slippage to entry price
                    entry_price_slipped = apply_slippage(current_close, True, True)
                    entry_fees = calculate_fees(entry_price_slipped * qty)
                    
                    position = "LONG"
                    entry_price = entry_price_slipped
                    entry_ts = current_candle.ts
                    position_quantity = qty
                    realized_equity -= entry_fees
                    total_fees += entry_fees
                    
                    append_event({"event": "PositionOpened", "side": "LONG", "ts": current_candle.ts,
                                 "price": entry_price, "quantity": qty, "stop": stop_price, "tp": tp_price})
                else:
                    # Calculate position size with risk management
                    qty, stop_price, tp_price = calculate_position_size(
                        equity=realized_equity,
                        entry_price=current_close,
                        risk_pct=risk_pct,
                        stop_bps=stop_bps,
                        tp_r=tp_r,
                        max_leverage=max_leverage,
                    )
                    
                    if qty is None:
                        append_event({"event": "RiskSizingSkipped", "reason": "invalid stop distance or qty"})
                        continue
                    
                    # Apply slippage to entry price
                    entry_price_slipped = apply_slippage(current_close, True, False)
                    entry_fees = calculate_fees(entry_price_slipped * qty)
                    
                    position = "SHORT"
                    entry_price = entry_price_slipped
                    entry_ts = current_candle.ts
                    position_quantity = qty
                    realized_equity -= entry_fees
                    total_fees += entry_fees
                    
                    append_event({"event": "PositionOpened", "side": "SHORT", "ts": current_candle.ts,
                                 "price": entry_price, "quantity": qty, "stop": stop_price, "tp": tp_price})
        
        # Record mark-to-market equity at this step
        equity_history.append({
            "ts": current_candle.ts,
            "equity": float(m2m_equity)
        })
        
        # Track max drawdown based on realized equity
        max_equity = max(max_equity, realized_equity)
        current_drawdown = (max_equity - realized_equity) / max_equity if max_equity > 0 else 0
        max_drawdown = max(max_drawdown, current_drawdown)
    
    # Close any open position at the final candle
    if position is not None:
        final_candle = candles[-1]
        final_close = float(final_candle.close)
        
        if position == "LONG":
            exit_price_slipped = apply_slippage(final_close, False, True)
            pnl = (exit_price_slipped - entry_price) * position_quantity
            exit_fees = calculate_fees(exit_price_slipped * position_quantity)
            
            trade = {
                "trade_id": str(uuid.uuid4()),
                "side": "LONG",
                "signal": "BUY",
                "entry": float(entry_price),
                "exit": float(exit_price_slipped),
                "price": float(exit_price_slipped),
                "quantity": float(position_quantity),
                "pnl": float(pnl - exit_fees),
                "fees": float(exit_fees),
                "entry_ts": entry_ts,
                "exit_ts": final_candle.ts,
                "timestamp": utc_ts(),
            }
            trades.append(trade)
            
            if pnl - exit_fees >= 0:
                wins += 1
            else:
                losses += 1
            
            realized_equity += pnl - exit_fees
            total_fees += exit_fees
            
            append_event({"event": "PositionClosed", "side": "LONG", "ts": final_candle.ts,
                         "price": exit_price_slipped, "pnl": pnl - exit_fees})
        else:  # SHORT
            exit_price_slipped = apply_slippage(final_close, False, False)
            pnl = (entry_price - exit_price_slipped) * position_quantity
            exit_fees = calculate_fees(exit_price_slipped * position_quantity)
            
            trade = {
                "trade_id": str(uuid.uuid4()),
                "side": "SHORT",
                "signal": "SELL",
                "entry": float(entry_price),
                "exit": float(exit_price_slipped),
                "price": float(exit_price_slipped),
                "quantity": float(position_quantity),
                "pnl": float(pnl - exit_fees),
                "fees": float(exit_fees),
                "entry_ts": entry_ts,
                "exit_ts": final_candle.ts,
                "timestamp": utc_ts(),
            }
            trades.append(trade)
            
            if pnl - exit_fees >= 0:
                wins += 1
            else:
                losses += 1
            
            realized_equity += pnl - exit_fees
            total_fees += exit_fees
            
            append_event({"event": "PositionClosed", "side": "SHORT", "ts": final_candle.ts,
                         "price": exit_price_slipped, "pnl": pnl - exit_fees})
    
    # Final equity is the realized equity (all positions closed)
    equity = realized_equity
    
    # Write equity.csv with mark-to-market data
    equity_csv_path = LATEST_DIR / "equity.csv"
    temp_equity = equity_csv_path.with_suffix(".tmp")
    try:
        with temp_equity.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["ts", "equity"])
            writer.writeheader()
            for eq in equity_history:
                writer.writerow(eq)
        temp_equity.replace(equity_csv_path)
    except Exception as e:
        if temp_equity.exists():
            temp_equity.unlink()
        raise RuntimeError(f"Failed to write equity.csv: {e}")
    
    # Calculate stats
    win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0.0
    net_pnl = equity - starting_balance
    
    stats = {
        "trades": len(trades),
        "wins": wins,
        "losses": losses,
        "win_rate": float(win_rate),
        "net_pnl": float(net_pnl),
        "fees_total": float(total_fees),
        "max_drawdown": float(max_drawdown),
        "starting_balance": float(starting_balance),
        "ending_balance": float(equity),
    }
    
    # Write stats.json
    stats_path = LATEST_DIR / "stats.json"
    temp_stats = stats_path.with_suffix(".tmp")
    try:
        with temp_stats.open("w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2)
        temp_stats.replace(stats_path)
    except Exception as e:
        if temp_stats.exists():
            temp_stats.unlink()
        raise RuntimeError(f"Failed to write stats.json: {e}")
    
    return {
        "trades": trades,
        "equity_history": equity_history,
        "stats": stats,
        "ending_balance": equity
    }


def run_live_paper_trading(
    candles: List[Candle],
    starting_balance: float,
    fees_bps: float,
    slip_bps: float,
    symbol: str,
    interval: str,
    source: str,
    risk_pct: float = 1.0,
    stop_bps: float = 30.0,
    tp_r: float = 1.5,
    max_leverage: float = 1.0,
    intrabar_mode: str = "conservative",
) -> tuple[List[Dict[str, Any]], float, Dict[str, Any]]:
    """
    Run live paper trading with persistent state and risk management.
    Returns (trades, ending_balance, state)
    """
    # Load or initialize state
    state_path = PAPER_DIR / "state.json"
    if state_path.exists():
        with state_path.open("r", encoding="utf-8") as f:
            state = json.load(f)
        # Ensure all required fields exist in loaded state
        state.setdefault("risk_pct", risk_pct)
        state.setdefault("stop_bps", stop_bps)
        state.setdefault("tp_r", tp_r)
        state.setdefault("max_leverage", max_leverage)
        state.setdefault("intrabar_mode", intrabar_mode)
        state.setdefault("realized_pnl", 0.0)
        state.setdefault("unrealized_pnl", 0.0)
        state.setdefault("net_pnl", 0.0)
        state.setdefault("fees_total", 0.0)
    else:
        state = {
            "equity": starting_balance,
            "position": None,
            "last_ts": None,
            "fees_bps": fees_bps,
            "slip_bps": slip_bps,
            "symbol": symbol,
            "interval": interval,
            "source": source,
            "risk_pct": risk_pct,
            "stop_bps": stop_bps,
            "tp_r": tp_r,
            "max_leverage": max_leverage,
            "intrabar_mode": intrabar_mode,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "net_pnl": 0.0,
            "fees_total": 0.0,
        }

    # Ensure paper directory exists
    PAPER_DIR.mkdir(exist_ok=True)

    # Helper function to calculate fees
    def calculate_fees(notional: float) -> float:
        return notional * (fees_bps / 10_000.0)

    # Helper function to apply slippage
    def apply_slippage(price: float, is_entry: bool, is_long: bool) -> float:
        slip_rate = slip_bps / 10_000.0
        if is_long:
            return price * (1.0 + slip_rate) if is_entry else price * (1.0 - slip_rate)
        else:
            return price * (1.0 - slip_rate) if is_entry else price * (1.0 + slip_rate)

    # Identify new candles
    last_ts = state.get("last_ts")
    new_candles = []
    for candle in candles:
        if last_ts is None or candle.ts > last_ts:
            new_candles.append(candle)

    if not new_candles:
        append_event({"event": "NoNewCandles", "last_ts": last_ts}, paper=True)
        return [], state["equity"], state

    # Process new candles
    trades = []
    for candle in new_candles:
        current_close = float(candle.close)
        current_high = float(candle.high)
        current_low = float(candle.low)
        
        # Compute SMAs
        closes = [float(c.close) for c in candles if c.ts <= candle.ts]
        fast_sma = sma(closes, 10)
        slow_sma = sma(closes, 30)
        
        if fast_sma is None or slow_sma is None:
            continue
        
        signal = "BUY" if fast_sma > slow_sma else "SELL"
        
        # Position management
        position = state.get("position")
        if position is None:
            # Open position with risk management
            if signal == "BUY":
                qty, stop_price, tp_price = calculate_position_size(
                    equity=state["equity"],
                    entry_price=current_close,
                    risk_pct=risk_pct,
                    stop_bps=stop_bps,
                    tp_r=tp_r,
                    max_leverage=max_leverage,
                )
                
                if qty is None:
                    append_event({"event": "RiskSizingSkipped", "reason": "invalid stop distance or qty"}, paper=True)
                    continue
                
                entry_price_slipped = apply_slippage(current_close, True, True)
                entry_fees = calculate_fees(entry_price_slipped * qty)
                
                state["position"] = {
                    "side": "LONG",
                    "entry_price": entry_price_slipped,
                    "entry_ts": candle.ts,
                    "quantity": qty,
                    "stop_price": stop_price,
                    "tp_price": tp_price,
                }
                state["equity"] -= entry_fees
                state["fees_total"] = state.get("fees_total", 0.0) + entry_fees
                
                append_event({"event": "PositionOpened", "side": "LONG", "ts": candle.ts,
                             "price": entry_price_slipped, "quantity": qty, "stop": stop_price, "tp": tp_price}, paper=True)
            elif signal == "SELL":
                qty, stop_price, tp_price = calculate_position_size(
                    equity=state["equity"],
                    entry_price=current_close,
                    risk_pct=risk_pct,
                    stop_bps=stop_bps,
                    tp_r=tp_r,
                    max_leverage=max_leverage,
                )
                
                if qty is None:
                    append_event({"event": "RiskSizingSkipped", "reason": "invalid stop distance or qty"}, paper=True)
                    continue
                
                entry_price_slipped = apply_slippage(current_close, True, False)
                entry_fees = calculate_fees(entry_price_slipped * qty)
                
                state["position"] = {
                    "side": "SHORT",
                    "entry_price": entry_price_slipped,
                    "entry_ts": candle.ts,
                    "quantity": qty,
                    "stop_price": stop_price,
                    "tp_price": tp_price,
                }
                state["equity"] -= entry_fees
                state["fees_total"] = state.get("fees_total", 0.0) + entry_fees
                
                append_event({"event": "PositionOpened", "side": "SHORT", "ts": candle.ts,
                             "price": entry_price_slipped, "quantity": qty, "stop": stop_price, "tp": tp_price}, paper=True)
        else:
            # Ensure position has required fields (backward compatibility)
            if "stop_price" not in position or "tp_price" not in position:
                # Recalculate stop/tp prices for existing positions
                qty, stop_price, tp_price = calculate_position_size(
                    equity=state["equity"],
                    entry_price=position["entry_price"],
                    risk_pct=risk_pct,
                    stop_bps=stop_bps,
                    tp_r=tp_r,
                    max_leverage=max_leverage,
                )
                position["stop_price"] = stop_price
                position["tp_price"] = tp_price
            
            # Check for stop/tp hits
            exit_reason = None
            exit_price = None
            
            if position["side"] == "LONG":
                stop_hit = current_low <= position["stop_price"]
                tp_hit = current_high >= position["tp_price"]
                
                if stop_hit and tp_hit:
                    # Both hit in same candle - use intrabar mode
                    if intrabar_mode == "conservative":
                        exit_reason = "STOP"
                        exit_price = position["stop_price"]
                    else:
                        exit_reason = "TP"
                        exit_price = position["tp_price"]
                elif stop_hit:
                    exit_reason = "STOP"
                    exit_price = position["stop_price"]
                elif tp_hit:
                    exit_reason = "TP"
                    exit_price = position["tp_price"]
            else:  # SHORT
                stop_hit = current_high >= position["stop_price"]
                tp_hit = current_low <= position["tp_price"]
                
                if stop_hit and tp_hit:
                    # Both hit in same candle - use intrabar mode
                    if intrabar_mode == "conservative":
                        exit_reason = "STOP"
                        exit_price = position["stop_price"]
                    else:
                        exit_reason = "TP"
                        exit_price = position["tp_price"]
                elif stop_hit:
                    exit_reason = "STOP"
                    exit_price = position["stop_price"]
                elif tp_hit:
                    exit_reason = "TP"
                    exit_price = position["tp_price"]
            
            # If exit triggered, close position
            if exit_reason is not None:
                exit_price_slipped = apply_slippage(exit_price, False, position["side"] == "LONG")
                
                if position["side"] == "LONG":
                    pnl = (exit_price_slipped - position["entry_price"]) * position["quantity"]
                else:
                    pnl = (position["entry_price"] - exit_price_slipped) * position["quantity"]
                
                exit_fees = calculate_fees(exit_price_slipped * position["quantity"])
                
                trade = {
                    "trade_id": str(uuid.uuid4()),
                    "side": position["side"],
                    "signal": "BUY" if position["side"] == "LONG" else "SELL",
                    "entry": float(position["entry_price"]),
                    "exit": float(exit_price_slipped),
                    "price": float(exit_price_slipped),
                    "quantity": float(position["quantity"]),
                    "pnl": float(pnl - exit_fees),
                    "fees": float(exit_fees),
                    "entry_ts": position["entry_ts"],
                    "exit_ts": candle.ts,
                    "timestamp": utc_ts(),
                    "exit_reason": exit_reason,
                    "stop_price": float(position["stop_price"]),
                    "tp_price": float(position["tp_price"]),
                }
                trades.append(trade)
                
                state["equity"] += pnl - exit_fees
                state["fees_total"] = state.get("fees_total", 0.0) + exit_fees
                state["realized_pnl"] = state.get("realized_pnl", 0.0) + (pnl - exit_fees)
                state["position"] = None
                
                append_event({"event": "PositionClosed", "side": position["side"], "ts": candle.ts,
                             "price": exit_price_slipped, "pnl": pnl - exit_fees, "reason": exit_reason}, paper=True)
            elif (position["side"] == "LONG" and signal == "SELL") or (position["side"] == "SHORT" and signal == "BUY"):
                # Crossover reversal - close at current close
                exit_price_slipped = apply_slippage(current_close, False, position["side"] == "LONG")
                
                if position["side"] == "LONG":
                    pnl = (exit_price_slipped - position["entry_price"]) * position["quantity"]
                else:
                    pnl = (position["entry_price"] - exit_price_slipped) * position["quantity"]
                
                exit_fees = calculate_fees(exit_price_slipped * position["quantity"])
                
                trade = {
                    "trade_id": str(uuid.uuid4()),
                    "side": position["side"],
                    "signal": "BUY" if position["side"] == "LONG" else "SELL",
                    "entry": float(position["entry_price"]),
                    "exit": float(exit_price_slipped),
                    "price": float(exit_price_slipped),
                    "quantity": float(position["quantity"]),
                    "pnl": float(pnl - exit_fees),
                    "fees": float(exit_fees),
                    "entry_ts": position["entry_ts"],
                    "exit_ts": candle.ts,
                    "timestamp": utc_ts(),
                    "exit_reason": "REVERSE",
                    "stop_price": float(position["stop_price"]),
                    "tp_price": float(position["tp_price"]),
                }
                trades.append(trade)
                
                state["equity"] += pnl - exit_fees
                state["fees_total"] = state.get("fees_total", 0.0) + exit_fees
                state["realized_pnl"] = state.get("realized_pnl", 0.0) + (pnl - exit_fees)
                state["position"] = None
                
                append_event({"event": "PositionClosed", "side": position["side"], "ts": candle.ts,
                             "price": exit_price_slipped, "pnl": pnl - exit_fees, "reason": "REVERSE"}, paper=True)
                
                # Open opposite position
                if signal == "BUY":
                    qty, stop_price, tp_price = calculate_position_size(
                        equity=state["equity"],
                        entry_price=current_close,
                        risk_pct=risk_pct,
                        stop_bps=stop_bps,
                        tp_r=tp_r,
                        max_leverage=max_leverage,
                    )
                    
                    if qty is None:
                        append_event({"event": "RiskSizingSkipped", "reason": "invalid stop distance or qty"}, paper=True)
                        continue
                    
                    entry_price_slipped = apply_slippage(current_close, True, True)
                    entry_fees = calculate_fees(entry_price_slipped * qty)
                    
                    state["position"] = {
                        "side": "LONG",
                        "entry_price": entry_price_slipped,
                        "entry_ts": candle.ts,
                        "quantity": qty,
                        "stop_price": stop_price,
                        "tp_price": tp_price,
                    }
                    state["equity"] -= entry_fees
                    state["fees_total"] = state.get("fees_total", 0.0) + entry_fees
                    
                    append_event({"event": "PositionOpened", "side": "LONG", "ts": candle.ts,
                                 "price": entry_price_slipped, "quantity": qty, "stop": stop_price, "tp": tp_price}, paper=True)
                else:
                    qty, stop_price, tp_price = calculate_position_size(
                        equity=state["equity"],
                        entry_price=current_close,
                        risk_pct=risk_pct,
                        stop_bps=stop_bps,
                        tp_r=tp_r,
                        max_leverage=max_leverage,
                    )
                    
                    if qty is None:
                        append_event({"event": "RiskSizingSkipped", "reason": "invalid stop distance or qty"}, paper=True)
                        continue
                    
                    entry_price_slipped = apply_slippage(current_close, True, False)
                    entry_fees = calculate_fees(entry_price_slipped * qty)
                    
                    state["position"] = {
                        "side": "SHORT",
                        "entry_price": entry_price_slipped,
                        "entry_ts": candle.ts,
                        "quantity": qty,
                        "stop_price": stop_price,
                        "tp_price": tp_price,
                    }
                    state["equity"] -= entry_fees
                    state["fees_total"] = state.get("fees_total", 0.0) + entry_fees
                    
                    append_event({"event": "PositionOpened", "side": "SHORT", "ts": candle.ts,
                                 "price": entry_price_slipped, "quantity": qty, "stop": stop_price, "tp": tp_price}, paper=True)

    # Update last_ts to the last processed candle
    state["last_ts"] = candles[-1].ts
    
    # Calculate unrealized PnL if position is open
    if state.get("position") is not None:
        position = state["position"]
        last_close = float(candles[-1].close)
        if position["side"] == "LONG":
            unrealized_pnl = (last_close - position["entry_price"]) * position["quantity"]
        else:
            unrealized_pnl = (position["entry_price"] - last_close) * position["quantity"]
        state["unrealized_pnl"] = unrealized_pnl
    else:
        state["unrealized_pnl"] = 0.0
    
    # Calculate net PnL
    state["net_pnl"] = state.get("realized_pnl", 0.0) + state.get("unrealized_pnl", 0.0)
    
    # Save state
    temp_state = state_path.with_suffix(".tmp")
    try:
        with temp_state.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        temp_state.replace(state_path)
    except Exception as e:
        if temp_state.exists():
            temp_state.unlink()
        raise RuntimeError(f"Failed to write state.json: {e}")
    
    # Append trades to paper/trades.csv
    trades_csv_path = PAPER_DIR / "trades.csv"
    if trades:
        fieldnames = ["trade_id", "side", "signal", "entry", "exit", "price", "quantity", "pnl", "fees",
                      "entry_ts", "exit_ts", "timestamp", "exit_reason", "stop_price", "tp_price"]
        temp_trades = trades_csv_path.with_suffix(".tmp")
        try:
            with temp_trades.open("a" if trades_csv_path.exists() else "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if not trades_csv_path.exists():
                    writer.writeheader()
                for trade in trades:
                    writer.writerow({k: v for k, v in trade.items() if k in fieldnames})
            temp_trades.replace(trades_csv_path)
        except Exception as e:
            if temp_trades.exists():
                temp_trades.unlink()
            raise RuntimeError(f"Failed to append to trades.csv: {e}")
    
    return trades, state["equity"], state


def generate_signal(candles: List[Candle]) -> Optional[str]:
    # Avoid lookahead: compute signal on candles[:-1]
    base = candles[:-1]
    if len(base) < 30:
        return None
    closes = [c.close for c in base]
    fast = sma(closes, 10)
    slow = sma(closes, 30)
    if fast is None or slow is None:
        return None
    return "BUY" if fast > slow else "SELL"


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


def write_trades_csv(trades: List[Dict[str, Any]]) -> None:
    p = LATEST_DIR / "trades.csv"
    # Define canonical trade schema - these are the only fields we write
    fieldnames = ["trade_id", "side", "signal", "entry", "exit", "price", "quantity", "pnl", "fees",
                  "entry_ts", "exit_ts", "timestamp"]
    
    # Use atomic write: write to temp file first, then replace
    temp_p = p.with_suffix(".tmp")
    try:
        with temp_p.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            for t in trades:
                # Ensure we only write the canonical fields
                filtered_trade = {k: v for k, v in t.items() if k in fieldnames}
                w.writerow(filtered_trade)
        # Atomic replace
        temp_p.replace(p)
    except Exception as e:
        # Clean up temp file if something went wrong
        if temp_p.exists():
            temp_p.unlink()
        raise RuntimeError(f"Failed to write trades.csv: {e}")


def write_state(state: Dict[str, Any]) -> None:
    with (LATEST_DIR / "state.json").open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def render_html(summary: Dict[str, Any], trades: List[Dict[str, Any]], error_message: str = "") -> None:
    events_tail = ""
    ep = LATEST_DIR / "events.jsonl"
    if ep.exists():
        events_tail = "\n".join(ep.read_text(encoding="utf-8").splitlines()[-80:])

    rows = ""
    # Show last 10 trades (newest first)
    display_trades = trades[-10:] if len(trades) > 10 else trades
    for t in display_trades:
        rows += (
            f"<tr><td>{t['trade_id']}</td><td>{t['side']}</td><td>{t['signal']}</td>"
            f"<td>${float(t['entry']):.2f}</td><td>${float(t['exit']):.2f}</td>"
            f"<td>{float(t['quantity']):.8f}</td><td>${float(t['pnl']):.2f}</td><td>${float(t['fees']):.2f}</td>"
            f"<td>{t['timestamp']}</td></tr>"
        )
    if not rows:
        rows = "<tr><td colspan='10'>No trades</td></tr>"

    # Error section if there was an error
    error_section = ""
    if error_message:
        error_section = f"""
    <div style="background: #ffebee; border: 1px solid #ef9a9a; padding: 15px; margin: 20px 0; border-radius: 4px;">
        <h3 style="color: #c62828; margin-top: 0;">Error</h3>
        <pre style="margin: 0; white-space: pre-wrap;">{error_message}</pre>
    </div>
"""

    # Equity curve visualization (if equity.csv exists)
    equity_chart = ""
    equity_csv = LATEST_DIR / "equity.csv"
    if equity_csv.exists():
        try:
            equity_data = []
            with equity_csv.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    equity_data.append((row["ts"], float(row["equity"])))
            
            if equity_data:
                # Normalize equity values for SVG scaling
                min_equity = min(e[1] for e in equity_data)
                max_equity = max(e[1] for e in equity_data)
                range_equity = max_equity - min_equity if max_equity != min_equity else 1
                
                # Create SVG points
                points = []
                for i, (ts, equity_val) in enumerate(equity_data):
                    x = i / (len(equity_data) - 1) * 100
                    y = 100 - ((equity_val - min_equity) / range_equity) * 100
                    points.append(f"{x},{y}")
                
                equity_chart = f"""
    <div class="section">
        <h2>Equity Curve</h2>
        <div style="background: white; border: 1px solid #e1e8ed; border-radius: 6px; padding: 15px; margin: 10px 0;">
            <svg width="100%" height="200" viewBox="0 0 100 100" preserveAspectRatio="none">
                <rect width="100%" height="100%" fill="#f8f9fa"/>
                <polyline points="{' '.join(points)}" fill="none" stroke="#3498db" stroke-width="2"/>
                <text x="50" y="15" text-anchor="middle" font-size="3" fill="#7f8c8d">Equity Curve</text>
                <text x="50" y="95" text-anchor="middle" font-size="2" fill="#7f8c8d">Time</text>
                <text x="5" y="50" text-anchor="start" font-size="2" fill="#7f8c8d" transform="rotate(-90 5,50)">Equity</text>
            </svg>
        </div>
    </div>
"""
        except Exception as e:
            append_event({"event": "EquityChartError", "message": str(e)})

    # Backtest stats section (if available)
    backtest_stats_section = ""
    stats_json = LATEST_DIR / "stats.json"
    if stats_json.exists():
        try:
            with stats_json.open("r", encoding="utf-8") as f:
                stats = json.load(f)
                win_rate_pct = stats.get("win_rate", 0.0) * 100
                max_drawdown_pct = stats.get("max_drawdown", 0.0) * 100
                
                backtest_stats_section = f"""
    <div class="section">
        <h2>Backtest Statistics</h2>
        <div class="cards">
            <div class="card">
                <div class="card-label">Total Trades</div>
                <div class="card-value">{stats.get('trades', 0)}</div>
            </div>
            <div class="card">
                <div class="card-label">Wins</div>
                <div class="card-value">{stats.get('wins', 0)}</div>
            </div>
            <div class="card">
                <div class="card-label">Losses</div>
                <div class="card-value">{stats.get('losses', 0)}</div>
            </div>
            <div class="card">
                <div class="card-label">Win Rate</div>
                <div class="card-value">{win_rate_pct:.1f}%</div>
            </div>
            <div class="card">
                <div class="card-label">Max Drawdown</div>
                <div class="card-value" style="color: #e74c3c;">{max_drawdown_pct:.2f}%</div>
            </div>
            <div class="card">
                <div class="card-label">Total Fees</div>
                <div class="card-value">${stats.get('fees_total', 0.0):.2f}</div>
            </div>
        </div>
    </div>
"""
        except Exception as e:
            append_event({"event": "StatsReadError", "message": str(e)})

    # Live mode section (if available)
    live_stats_section = ""
    if summary.get("mode") == "live":
        position = summary.get("position")
        position_info = "flat"
        if position is not None:
            position_info = f"{position['side']} @ ${position['entry_price']:.2f} ({position['quantity']:.8f})"
        
        live_stats_section = f"""
    <div class="section">
        <h2>Live Paper Trading</h2>
        <div class="cards">
            <div class="card">
                <div class="card-label">Position</div>
                <div class="card-value">{position_info}</div>
            </div>
            <div class="card">
                <div class="card-label">Realized PnL</div>
                <div class="card-value">${summary.get('realized_pnl', 0.0):.2f}</div>
            </div>
            <div class="card">
                <div class="card-label">Unrealized PnL</div>
                <div class="card-value">${summary.get('unrealized_pnl', 0.0):.2f}</div>
            </div>
            <div class="card">
                <div class="card-label">Net PnL</div>
                <div class="card-value">${summary.get('net_pnl', 0.0):.2f}</div>
            </div>
            <div class="card">
                <div class="card-label">Total Fees</div>
                <div class="card-value">${summary.get('fees_total', 0.0):.2f}</div>
            </div>
        </div>
    </div>
"""

    # Enhanced metric cards with backtest stats
    win_rate_card = ""
    max_drawdown_card = ""
    fees_total_card = ""
    
    if stats_json.exists():
        try:
            with stats_json.open("r", encoding="utf-8") as f:
                stats = json.load(f)
                win_rate_pct = stats.get("win_rate", 0.0) * 100
                max_drawdown_pct = stats.get("max_drawdown", 0.0) * 100
                
                win_rate_card = f"""
            <div class="card">
                <div class="card-label">Win Rate</div>
                <div class="card-value">{win_rate_pct:.1f}%</div>
            </div>
"""
                max_drawdown_card = f"""
            <div class="card">
                <div class="card-label">Max Drawdown</div>
                <div class="card-value" style="color: #e74c3c;">{max_drawdown_pct:.2f}%</div>
            </div>
"""
                fees_total_card = f"""
            <div class="card">
                <div class="card-label">Total Fees</div>
                <div class="card-value">${stats.get('fees_total', 0.0):.2f}</div>
            </div>
"""
        except Exception as e:
            append_event({"event": "StatsReadError", "message": str(e)})
    
    # Mode card
    mode_card = ""
    if summary.get("mode") == "live":
        mode_card = """
        <div class="card">
            <div class="card-label">Mode</div>
            <div class="card-value" style="color: #e74c3c;">live</div>
        </div>
"""
    
    # Risk settings cards
    risk_settings_section = ""
    if summary.get("mode") in ["live", "backtest"]:
        risk_settings_section = f"""
    <div class="section">
        <h2>Risk Settings</h2>
        <div class="cards">
            <div class="card">
                <div class="card-label">Risk %</div>
                <div class="card-value">{summary.get('risk_pct', 1.0)}%</div>
            </div>
            <div class="card">
                <div class="card-label">Stop (bps)</div>
                <div class="card-value">{summary.get('stop_bps', 30.0)} bps</div>
            </div>
            <div class="card">
                <div class="card-label">TP Ratio</div>
                <div class="card-value">{summary.get('tp_r', 1.5)}</div>
            </div>
            <div class="card">
                <div class="card-label">Max Leverage</div>
                <div class="card-value">{summary.get('max_leverage', 1.0)}x</div>
            </div>
            <div class="card">
                <div class="card-label">Intrabar Mode</div>
                <div class="card-value">{summary.get('intrabar_mode', 'conservative')}</div>
            </div>
        </div>
    </div>
"""
    
    # Open position details
    open_position_section = ""
    if summary.get("mode") == "live" and summary.get("position"):
        position = summary["position"]
        open_position_section = f"""
    <div class="section">
        <h2>Open Position</h2>
        <div class="cards">
            <div class="card">
                <div class="card-label">Side</div>
                <div class="card-value">{position['side']}</div>
            </div>
            <div class="card">
                <div class="card-label">Entry</div>
                <div class="card-value">${position['entry_price']:.2f}</div>
            </div>
            <div class="card">
                <div class="card-label">Stop</div>
                <div class="card-value">${position['stop_price']:.2f}</div>
            </div>
            <div class="card">
                <div class="card-label">TP</div>
                <div class="card-value">${position['tp_price']:.2f}</div>
            </div>
            <div class="card">
                <div class="card-label">Quantity</div>
                <div class="card-value">{position['quantity']:.8f}</div>
            </div>
        </div>
    </div>
"""

    # Improved CSS with system font stack and better typography
    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Run Summary</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
      line-height: 1.6;
      color: #333;
      max-width: 1200px;
      margin: 0 auto;
      padding: 20px;
    }}
    
    h1, h2, h3 {{
      color: #2c3e50;
      font-weight: 600;
    }}
    
    h1 {{
      border-bottom: 2px solid #eee;
      padding-bottom: 10px;
    }}
    
    /* Metric cards */
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 15px;
      margin: 20px 0;
    }}
    
    .card {{
      background: white;
      border: 1px solid #e1e8ed;
      border-radius: 6px;
      padding: 15px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }}
    
    .card-label {{
      font-size: 0.8em;
      color: #7f8c8d;
      text-transform: uppercase;
      font-weight: 600;
      margin-bottom: 5px;
    }}
    
    .card-value {{
      font-size: 1.3em;
      font-weight: 500;
      color: #2c3e50;
    }}
    
    /* Table styling */
    table {{
      border-collapse: collapse;
      width: 100%;
      margin: 20px 0;
      font-size: 0.95em;
    }}
    
    th, td {{
      border: 1px solid #e1e8ed;
      padding: 12px;
      text-align: left;
    }}
    
    th {{
      background: #f8f9fa;
      font-weight: 600;
      color: #2c3e50;
      text-transform: uppercase;
      font-size: 0.85em;
    }}
    
    tr:nth-child(even) {{
      background-color: #fafafa;
    }}
    
    tr:hover {{
      background-color: #f5f7fa;
    }}
    
    /* Monospace for IDs and timestamps */
    td:nth-child(1), td:nth-child(9) {{
      font-family: 'Courier New', Courier, monospace;
      font-size: 0.9em;
    }}
    
    /* Events section */
    pre {{
      background: #f8f9fa;
      padding: 15px;
      border-radius: 4px;
      overflow: auto;
      font-size: 0.85em;
      line-height: 1.5;
      border: 1px solid #e1e8ed;
    }}
    
    /* Spacing */
    .section {{
      margin: 30px 0;
    }}
    
    .meta {{
      color: #7f8c8d;
      margin-bottom: 20px;
      font-size: 0.9em;
    }}
    
    /* Collapsible events */
    details {{
      border: 1px solid #e1e8ed;
      border-radius: 6px;
      padding: 10px;
      margin: 10px 0;
    }}
    
    summary {{
      font-weight: 600;
      cursor: pointer;
      color: #2c3e50;
    }}
  </style>
</head>
<body>
  <h1>Run Summary</h1>
  
  {error_section}
  
  <div class="cards">
      <div class="card">
          <div class="card-label">Run ID</div>
          <div class="card-value">{summary['run_id'][:8]}</div>
      </div>
      <div class="card">
          <div class="card-label">Mode</div>
          <div class="card-value" style="color: {'#e74c3c' if summary.get('mode') == 'live' else '#2c3e50'};">{summary.get('mode', 'single')}</div>
      </div>
      <div class="card">
          <div class="card-label">Source</div>
          <div class="card-value">{summary['source']}</div>
      </div>
      <div class="card">
          <div class="card-label">Symbol</div>
          <div class="card-value">{summary['symbol']}</div>
      </div>
      <div class="card">
          <div class="card-label">Interval</div>
          <div class="card-value">{summary['interval']}</div>
      </div>
      <div class="card">
          <div class="card-label">Candles</div>
          <div class="card-value">{summary['candle_count']}</div>
      </div>
      <div class="card">
          <div class="card-label">Start Balance</div>
          <div class="card-value">${summary['starting_balance']:.2f}</div>
      </div>
      <div class="card">
          <div class="card-label">End Balance</div>
          <div class="card-value">${summary['ending_balance']:.2f}</div>
      </div>
      <div class="card">
          <div class="card-label">Net PnL</div>
          <div class="card-value" style="color: {'#2ecc71' if summary['net_pnl'] >= 0 else '#e74c3c'};">
              ${summary['net_pnl']:.2f}
          </div>
      </div>
      {win_rate_card}
      {max_drawdown_card}
      <div class="card">
          <div class="card-label">Fees (bps)</div>
          <div class="card-value">${summary['fees_bps']} bps</div>
      </div>
      <div class="card">
          <div class="card-label">Slippage (bps)</div>
          <div class="card-value">${summary['slip_bps']} bps</div>
      </div>
      {fees_total_card}
  </div>

  {equity_chart}
  {risk_settings_section}
  {open_position_section}
  {backtest_stats_section}
  {live_stats_section}

  <div class="section">
    <h2>Last 10 Trades</h2>
    <table>
      <thead>
        <tr>
          <th>Trade ID</th><th>Side</th><th>Signal</th><th>Entry</th><th>Exit</th>
          <th>Quantity</th><th>PnL</th><th>Fees</th><th>Timestamp</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </div>

  <div class="section">
    <details>
      <summary>Events Tail (click to expand)</summary>
      <pre>{events_tail}</pre>
    </details>
  </div>
</body>
</html>
"""
    
    # Use atomic write for HTML too
    temp_p = (LATEST_DIR / "summary.html").with_suffix(".tmp")
    try:
        temp_p.write_text(html, encoding="utf-8")
        temp_p.replace(LATEST_DIR / "summary.html")
    except Exception as e:
        if temp_p.exists():
            temp_p.unlink()
        raise RuntimeError(f"Failed to write summary.html: {e}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["mock", "bitunix"], default="mock")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--interval", default="1m")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--fees-bps", type=float, default=2.0)   # 2 bps per side (simple)
    ap.add_argument("--slip-bps", type=float, default=0.5)   # tiny adverse slip
    ap.add_argument("--backtest", type=int, default=0, help="Backtest mode: 0=single trade (default), N=backtest last N candles")
    ap.add_argument("--backtest-mode", choices=["bar", "position"], default="position",
                   help="Backtest strategy: bar (one trade per bar) or position (position management)")
    ap.add_argument("--mode", choices=["single", "backtest", "live"], default=None,
                   help="Run mode: single (default), backtest, or live paper trading")
    ap.add_argument("--risk-pct", type=float, default=1.0, help="% equity risked per trade")
    ap.add_argument("--stop-bps", type=float, default=30.0, help="stop distance in bps from entry (0.30%)")
    ap.add_argument("--tp-r", type=float, default=1.5, help="take profit = stop_distance * tp-r")
    ap.add_argument("--max-leverage", type=float, default=1.0, help="cap notional: qty*entry <= equity*max_leverage")
    ap.add_argument("--intrabar-mode", choices=["conservative", "optimistic"], default="conservative",
                   help="conservative: stop first; optimistic: tp first")
    args = ap.parse_args()

    # Ensure runs/latest exists before we start
    RUNS_DIR.mkdir(exist_ok=True)
    LATEST_DIR.mkdir(parents=True, exist_ok=True)

    run_id = str(uuid.uuid4())
    starting_balance = 10_000.0
    error_message = ""

    # Determine mode
    if args.mode is None:
        if args.backtest > 0:
            mode = "backtest"
        else:
            mode = "single"
    else:
        mode = args.mode

    append_event({"event": "RunStarted", "run_id": run_id, "source": args.source, "symbol": args.symbol, "interval": args.interval, "backtest": args.backtest, "mode": mode})

    try:
        if args.source == "bitunix":
            limit = min(max(int(args.limit), 2), 200)
            candles = load_bitunix_candles(args.symbol, args.interval, limit)
        else:
            candles = load_mock_candles(max(int(args.limit), 50))

        append_event({"event": "MarketDataLoaded", "source": args.source, "symbol": args.symbol, "interval": args.interval, "count": len(candles)})

        # Normalize candle order (handle newest-first if needed)
        candles = normalize_candle_order(candles)
         
        if len(candles) < 2:
            raise RuntimeError("Need at least 2 candles to simulate a one-bar trade")

        if mode == "live":
            # Live paper trading mode
            trades, ending_balance, state = run_live_paper_trading(
                candles=candles,
                starting_balance=starting_balance,
                fees_bps=float(args.fees_bps),
                slip_bps=float(args.slip_bps),
                symbol=args.symbol,
                interval=args.interval,
                source=args.source,
                risk_pct=float(args.risk_pct),
                stop_bps=float(args.stop_bps),
                tp_r=float(args.tp_r),
                max_leverage=float(args.max_leverage),
                intrabar_mode=args.intrabar_mode,
            )
            append_event({"event": "LivePaperFinished", "trades": len(trades), "ending_balance": ending_balance}, paper=True)
        elif mode == "backtest":
            # Backtest mode
            append_event({"event": "BacktestStarted", "candles": len(candles), "backtest": args.backtest,
                         "mode": args.backtest_mode})
            
            # Cap backtest to available candles
            backtest_candles = min(args.backtest, len(candles))
            backtest_slice = candles[-backtest_candles:] if backtest_candles > 0 else candles
            
            # Use appropriate backtest function based on mode
            if args.backtest_mode == "bar":
                backtest_result = run_backtest_bar_mode(
                    candles=backtest_slice,
                    starting_balance=starting_balance,
                    fees_bps=float(args.fees_bps),
                    slip_bps=float(args.slip_bps)
                )
            else:  # position mode
                backtest_result = run_backtest_position_mode(
                    candles=backtest_slice,
                    starting_balance=starting_balance,
                    fees_bps=float(args.fees_bps),
                    slip_bps=float(args.slip_bps),
                    risk_pct=float(args.risk_pct),
                    stop_bps=float(args.stop_bps),
                    tp_r=float(args.tp_r),
                    max_leverage=float(args.max_leverage),
                    intrabar_mode=args.intrabar_mode,
                )
            
            trades = backtest_result["trades"]
            ending_balance = backtest_result["ending_balance"]
            stats = backtest_result["stats"]
            
            append_event({"event": "BacktestFinished", "trades": len(trades), "net_pnl": stats["net_pnl"],
                         "mode": args.backtest_mode})
            
        elif mode == "single":
            # Single trade mode (original behavior)
            last = candles[-1]
            prev = candles[-2]
            append_event({"event": "LastCandle", "ts": last.ts, "close": last.close})
            append_event({"event": "PrevCandle", "ts": prev.ts, "close": prev.close})

            signal = generate_signal(candles)
            append_event({"event": "SignalGenerated", "signal": signal})

            trades: List[Dict[str, Any]] = []
            ending_balance = starting_balance

            if signal in ("BUY", "SELL"):
                trade = simulate_trade_one_bar(
                    signal=signal,
                    entry_px=float(prev.close),
                    exit_px=float(last.close),
                    starting_balance=starting_balance,
                    fees_bps=float(args.fees_bps),
                    slip_bps=float(args.slip_bps),
                )
                trades.append(trade)
                ending_balance = starting_balance + float(trade["pnl"])
                append_event({"event": "TradeSimulated", "trade": trade})
            else:
                append_event({"event": "NoTrade", "reason": "insufficient data for SMA(10/30)"})
        else:
            # Backtest mode
            append_event({"event": "BacktestStarted", "candles": len(candles), "backtest": args.backtest,
                         "mode": args.backtest_mode})
            
            # Cap backtest to available candles
            backtest_candles = min(args.backtest, len(candles))
            backtest_slice = candles[-backtest_candles:] if backtest_candles > 0 else candles
            
            # Use appropriate backtest function based on mode
            if args.backtest_mode == "bar":
                backtest_result = run_backtest_bar_mode(
                    candles=backtest_slice,
                    starting_balance=starting_balance,
                    fees_bps=float(args.fees_bps),
                    slip_bps=float(args.slip_bps)
                )
            else:  # position mode
                backtest_result = run_backtest_position_mode(
                    candles=backtest_slice,
                    starting_balance=starting_balance,
                    fees_bps=float(args.fees_bps),
                    slip_bps=float(args.slip_bps)
                )
            
            trades = backtest_result["trades"]
            ending_balance = backtest_result["ending_balance"]
            stats = backtest_result["stats"]
            
            append_event({"event": "BacktestFinished", "trades": len(trades), "net_pnl": stats["net_pnl"],
                         "mode": args.backtest_mode})

        # Write trades.csv with atomic write
        write_trades_csv(trades)

        # Prepare summary
        last_candle = candles[-1]
        summary = {
            "run_id": run_id,
            "source": args.source,
            "symbol": args.symbol,
            "interval": args.interval,
            "candle_count": len(candles),
            "last_ts": str(last_candle.ts),
            "last_close": float(last_candle.close),
            "fees_bps": float(args.fees_bps),
            "slip_bps": float(args.slip_bps),
            "starting_balance": starting_balance,
            "ending_balance": float(ending_balance),
            "net_pnl": float(ending_balance - starting_balance),
            "trades": len(trades),
            "mode": mode,
        }
         
        # Add backtest stats if in backtest mode
        if mode == "backtest":
            stats_path = LATEST_DIR / "stats.json"
            if stats_path.exists():
                with stats_path.open("r", encoding="utf-8") as f:
                    backtest_stats = json.load(f)
                    summary.update({
                        "win_rate": backtest_stats.get("win_rate", 0.0),
                        "max_drawdown": backtest_stats.get("max_drawdown", 0.0),
                        "fees_total": backtest_stats.get("fees_total", 0.0),
                    })
        
        # Add live paper trading stats if in live mode
        if mode == "live":
            summary.update({
                "position": state.get("position"),
                "realized_pnl": state.get("realized_pnl", 0.0),
                "unrealized_pnl": state.get("unrealized_pnl", 0.0),
                "net_pnl": state.get("net_pnl", 0.0),
                "fees_total": state.get("fees_total", 0.0),
            })
        
        write_state({"summary": summary})
        
        # Always write summary.html, even if we succeed
        render_html(summary, trades, error_message)

        append_event({"event": "RunFinished", "run_id": run_id})
        return 0

    except Exception as e:
        error_message = str(e)
        # Include traceback in events for debugging
        import traceback
        tb_str = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        append_event({"event": "Error", "message": error_message, "trace": tb_str[-500:]})
        
        # Always write summary.html even on error
        summary = {
            "run_id": run_id,
            "source": args.source,
            "symbol": args.symbol,
            "interval": args.interval,
            "candle_count": 0,
            "last_ts": "N/A",
            "last_close": 0.0,
            "fees_bps": float(args.fees_bps),
            "slip_bps": float(args.slip_bps),
            "starting_balance": starting_balance,
            "ending_balance": starting_balance,
            "net_pnl": 0.0,
            "trades": 0,
        }
        render_html(summary, [], error_message)
        
        print("ERROR:", error_message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
