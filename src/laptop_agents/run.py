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


# Required keys for valid events.jsonl lines
REQUIRED_EVENT_KEYS = {"event", "timestamp"}

# Required columns for trades.csv
REQUIRED_TRADE_COLUMNS = {"trade_id", "side", "signal", "entry", "exit", "quantity", "pnl", "fees", "timestamp"}


def validate_events_jsonl(events_path: Path) -> tuple[bool, str]:
    """Validate events.jsonl - each line must be valid JSON with required keys."""
    if not events_path.exists():
        return False, f"events.jsonl does not exist at {events_path}"
    
    valid_lines = 0
    invalid_lines = 0
    with events_path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                # Check for required keys
                missing_keys = REQUIRED_EVENT_KEYS - set(obj.keys())
                if missing_keys:
                    invalid_lines += 1
                    append_event({"event": "EventsValidationError", "line": line_num, "missing_keys": list(missing_keys)})
                else:
                    valid_lines += 1
            except json.JSONDecodeError:
                invalid_lines += 1
                append_event({"event": "EventsValidationError", "line": line_num, "error": "invalid JSON"})
    
    if invalid_lines > 0:
        return False, f"events.jsonl: {valid_lines} valid, {invalid_lines} invalid lines"
    if valid_lines == 0:
        return False, "events.jsonl: no valid lines found"
    return True, f"events.jsonl: {valid_lines} valid lines"


def validate_trades_csv(trades_path: Path) -> tuple[bool, str]:
    """Validate trades.csv - must have required header columns and at least 1 data row."""
    if not trades_path.exists():
        return False, f"trades.csv does not exist at {trades_path}"
    
    try:
        with trades_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames or []
            
            # Check required columns
            missing_cols = REQUIRED_TRADE_COLUMNS - set(header)
            if missing_cols:
                return False, f"trades.csv: missing required columns: {sorted(missing_cols)}"
            
            # Count data rows
            rows = list(reader)
            if len(rows) == 0:
                # Check for "no trades" marker in header or special row
                return False, "trades.csv: no data rows (no trades executed)"
            
            return True, f"trades.csv: {len(rows)} trades, all required columns present"
    except Exception as e:
        return False, f"trades.csv: validation error - {e}"


def validate_summary_html(summary_path: Path) -> tuple[bool, str]:
    """Validate summary.html - must exist and contain recognizable marker."""
    if not summary_path.exists():
        return False, f"summary.html does not exist at {summary_path}"
    
    content = summary_path.read_text(encoding="utf-8")
    # Check for recognizable markers
    markers = ["<title>Run Summary</title>", "Run Summary", "run_id"]
    for marker in markers:
        if marker in content:
            return True, f"summary.html: contains marker '{marker}'"
    
    return False, "summary.html: no recognizable marker found"


def run_orchestrated_mode(
    symbol: str,
    interval: str,
    source: str,
    limit: int,
    fees_bps: float,
    slip_bps: float,
) -> tuple[bool, str]:
    """Run orchestrated mode - end-to-end execution with artifact validation."""
    run_id = str(uuid.uuid4())
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Create run-specific LATEST_DIR symlink/copy
    reset_latest_dir()
    
    append_event({"event": "OrchestratedRunStarted", "run_id": run_id, "source": source, "symbol": symbol, "interval": interval})
    
    try:
        # Load candles
        if source == "bitunix":
            candles = load_bitunix_candles(symbol, interval, limit)
        else:
            candles = load_mock_candles(max(int(limit), 50))
        
        candles = normalize_candle_order(candles)
        
        if len(candles) < 2:
            raise RuntimeError("Need at least 2 candles to run orchestrated mode")
        
        append_event({"event": "MarketDataLoaded", "source": source, "symbol": symbol, "count": len(candles)})
        
        # Run live trading cycle (single iteration) using the same code path as live mode
        # Use run_live_paper_trading with a fresh state for this orchestrated run
        starting_balance = 10_000.0
        
        # Ensure we start with a fresh state by removing any existing paper state
        state_path = PAPER_DIR / "state.json"
        if state_path.exists():
            state_path.unlink()
        
        # Call run_live_paper_trading which will use the same logic as live mode
        trades, ending_balance, state = run_live_paper_trading(
            candles=candles,
            starting_balance=starting_balance,
            fees_bps=fees_bps,
            slip_bps=slip_bps,
            symbol=symbol,
            interval=interval,
            source=source,
            risk_pct=1.0,
            stop_bps=30.0,
            tp_r=1.5,
            max_leverage=1.0,
            intrabar_mode="conservative",
        )
        
        # Write trades.csv to LATEST_DIR
        # Note: run_live_paper_trading writes trades to paper/trades.csv, so we need to copy them
        paper_trades_csv = PAPER_DIR / "trades.csv"
        if paper_trades_csv.exists():
            # Copy trades from paper directory to latest directory
            shutil.copy2(paper_trades_csv, LATEST_DIR / "trades.csv")
        else:
            # If no trades were generated, create an empty trades.csv
            write_trades_csv(trades)
        
        append_event({"event": "OrchestratedLiveCycleFinished", "trades": len(trades), "ending_balance": ending_balance})
        
        # Write trades.csv (already done in run_backtest_position_mode to LATEST_DIR)
        # But also copy to run_dir
        trades_csv_src = LATEST_DIR / "trades.csv"
        if trades_csv_src.exists():
            shutil.copy2(trades_csv_src, run_dir / "trades.csv")
        
        # Copy events.jsonl
        events_src = LATEST_DIR / "events.jsonl"
        if events_src.exists():
            shutil.copy2(events_src, run_dir / "events.jsonl")
        
        # Copy other artifacts
        equity_src = LATEST_DIR / "equity.csv"
        if equity_src.exists():
            shutil.copy2(equity_src, run_dir / "equity.csv")
        
        stats_src = LATEST_DIR / "stats.json"
        if stats_src.exists():
            shutil.copy2(stats_src, run_dir / "stats.json")
        
        # Write summary.html
        last_candle = candles[-1]
        summary = {
            "run_id": run_id,
            "source": source,
            "symbol": symbol,
            "interval": interval,
            "candle_count": len(candles),
            "last_ts": str(last_candle.ts),
            "last_close": float(last_candle.close),
            "fees_bps": fees_bps,
            "slip_bps": slip_bps,
            "starting_balance": 10_000.0,
            "ending_balance": float(ending_balance),
            "net_pnl": float(ending_balance - 10_000.0),
            "trades": len(trades),
            "mode": "orchestrated",
        }
        write_state({"summary": summary})
        render_html(summary, trades, "")
        
        # Copy summary.html to run_dir
        summary_src = LATEST_DIR / "summary.html"
        if summary_src.exists():
            shutil.copy2(summary_src, run_dir / "summary.html")
        
        # Validate artifacts
        events_valid, events_msg = validate_events_jsonl(run_dir / "events.jsonl")
        trades_valid, trades_msg = validate_trades_csv(run_dir / "trades.csv")
        summary_valid, summary_msg = validate_summary_html(run_dir / "summary.html")
        
        append_event({"event": "ArtifactValidation", "events": events_msg, "trades": trades_msg, "summary": summary_msg})
        
        if not (events_valid and trades_valid and summary_valid):
            errors = []
            if not events_valid:
                errors.append(f"events.jsonl: {events_msg}")
            if not trades_valid:
                errors.append(f"trades.csv: {trades_msg}")
            if not summary_valid:
                errors.append(f"summary.html: {summary_msg}")
            raise RuntimeError(f"Artifact validation failed: {'; '.join(errors)}")
        
        append_event({"event": "OrchestratedRunFinished", "run_id": run_id, "trades": len(trades), "ending_balance": ending_balance})
        
        return True, f"Orchestrated run completed successfully. Run ID: {run_id}"
        
    except Exception as e:
        append_event({"event": "OrchestratedRunError", "error": str(e)})
        return False, str(e)


def check_bitunix_config() -> tuple[bool, str]:
    """Check if bitunix configuration is available."""
    import os
    api_key = os.environ.get("BITUNIX_API_KEY", "")
    secret_key = os.environ.get("BITUNIX_SECRET_KEY", "")
    
    if not api_key or not secret_key:
        return False, "Bitunix API credentials not configured. Set BITUNIX_API_KEY and BITUNIX_SECRET_KEY environment variables."
    return True, "Bitunix configured"


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
    is_long: bool = True,
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Calculate position size, stop price, and take-profit price.
    Returns (qty, stop_price, tp_price) or (None, None, None) if invalid.
    
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


def parse_grid(grid_str: str, max_candidates: int = 200) -> list[dict[str, Any]]:
    """
    Parse grid string into parameter combinations.
    Supports multiple formats:
      - sma=10,30;12,36;15,45 (multiple pairs separated by semicolon)
      - sma=10=30;12=36 (fast=slow format)
      - stop=20,30,40 (comma-separated values)
      - tp=1.0,1.5,2.0 (comma-separated values)
    """
    params = {}
    
    # Parse each key=value pair
    for part in grid_str.split(";"):
        if "=" not in part:
            continue
        key, values_str = part.split("=", 1)
        key = key.strip().lower()
        
        # Handle SMA pairs (fast,slow)
        if key == "sma":
            sma_pairs = []
            # Try both formats: fast=slow and fast,slow
            for pair in values_str.split(","):
                pair = pair.strip()
                if "=" in pair:
                    # Format: fast=slow (e.g., 10=30)
                    fast, slow = pair.split("=", 1)
                    try:
                        sma_pairs.append((int(fast.strip()), int(slow.strip())))
                    except ValueError:
                        raise ValueError(f"Invalid SMA pair format: {pair}. Expected format like '10=30' or '10,30'")
                elif pair:  # Non-empty string
                    # Format: fast,slow (e.g., 10,30) - but this is a single value in comma-separated list
                    # This format is not supported in this context, need to use semicolon separation
                    pass
            
            # Also try parsing as space/comma separated pairs
            if not sma_pairs:
                # Try format: 10,30 12,36 15,45 (space separated pairs)
                for pair in values_str.split():
                    if "," in pair:
                        parts = pair.split(",")
                        if len(parts) == 2:
                            try:
                                sma_pairs.append((int(parts[0].strip()), int(parts[1].strip())))
                            except ValueError:
                                raise ValueError(f"Invalid SMA pair format: {pair}. Expected format like '10,30'")
            
            if not sma_pairs:
                raise ValueError(f"No valid SMA pairs found in: {values_str}. Use formats like '10=30' or '10,30 12,36'")
            
            params[key] = sma_pairs
        else:
            # Handle other parameters as lists
            values = []
            for val in values_str.split(","):
                val = val.strip()
                if val:  # Skip empty values
                    try:
                        if key in ["stop", "tp"]:
                            values.append(float(val))
                        else:
                            values.append(val)
                    except ValueError:
                        raise ValueError(f"Invalid {key} value: {val}. Expected numeric value")
            params[key] = values
    
    # Generate all combinations
    combinations = []
    sma_pairs = params.get("sma", [])
    stop_values = params.get("stop", [])
    tp_values = params.get("tp", [])
    
    # Cap total combinations to max_candidates
    total_combos = len(sma_pairs) * len(stop_values) * len(tp_values)
    if total_combos > max_candidates:
        # Downsample to keep under max_candidates
        import math
        reduction_factor = math.ceil(math.sqrt(total_combos / max_candidates))
        sma_pairs = sma_pairs[::reduction_factor]
        stop_values = stop_values[::reduction_factor]
        tp_values = tp_values[::reduction_factor]
        actual_combos = len(sma_pairs) * len(stop_values) * len(tp_values)
        append_event({"event": "ValidationCandidateCount", "original": total_combos, "reduced": actual_combos, "max_allowed": max_candidates})
    
    for sma_pair in sma_pairs:
        for stop_val in stop_values:
            for tp_val in tp_values:
                combinations.append({
                    "fast_sma": sma_pair[0],
                    "slow_sma": sma_pair[1],
                    "stop_bps": stop_val,
                    "tp_r": tp_val,
                })
    
    if not combinations:
        raise ValueError("Grid parsing resulted in 0 combinations. Check your grid format and values.")
    
    return combinations


def run_backtest_on_segment(
    candles: List[Candle],
    starting_balance: float,
    fees_bps: float,
    slip_bps: float,
    risk_pct: float,
    fast_sma: int,
    slow_sma: int,
    stop_bps: float,
    tp_r: float,
    max_leverage: float,
    intrabar_mode: str,
) -> Dict[str, Any]:
    """
    Run backtest on a specific segment with given parameters.
    Computes indicators only from candles in this segment (no lookahead).
    """
    if len(candles) < max(fast_sma, slow_sma) + 1:
        return {
            "net_pnl": 0.0,
            "max_drawdown": 0.0,
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "fees_total": 0.0,
            "equity_history": [],
        }
    
    # Normalize candle order (defensive)
    candles = normalize_candle_order(candles)
    
    # Initialize
    equity = starting_balance
    realized_equity = starting_balance
    equity_history = []
    trades = []
    
    # Position tracking
    position = None
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
    
    # Helper functions
    def calculate_fees(notional: float) -> float:
        return notional * (fees_bps / 10_000.0)
    
    def apply_slippage(price: float, is_entry: bool, is_long: bool) -> float:
        slip_rate = slip_bps / 10_000.0
        if is_long:
            return price * (1.0 + slip_rate) if is_entry else price * (1.0 - slip_rate)
        else:
            return price * (1.0 - slip_rate) if is_entry else price * (1.0 + slip_rate)
    
    # Backtest loop
    for i in range(len(candles)):
        current_candle = candles[i]
        current_close = float(current_candle.close)
        current_high = float(current_candle.high)
        current_low = float(current_candle.low)
        
        # Compute SMAs only from candles up to current index (no lookahead)
        closes = [float(c.close) for c in candles[:i+1]]
        fast_sma_val = sma(closes, fast_sma)
        slow_sma_val = sma(closes, slow_sma)
        
        if fast_sma_val is None or slow_sma_val is None:
            # Record equity even if no signal yet
            equity_history.append({"ts": current_candle.ts, "equity": float(realized_equity)})
            continue
        
        # Generate signal
        signal = "BUY" if fast_sma_val > slow_sma_val else "SELL"
        
        # Mark-to-market
        if position is not None:
            if position == "LONG":
                unrealized_pnl = (current_close - entry_price) * position_quantity
            else:
                unrealized_pnl = (entry_price - current_close) * position_quantity
            m2m_equity = realized_equity + unrealized_pnl
        else:
            m2m_equity = realized_equity
        
        # Position management
        if position is None:
            if signal == "BUY":
                qty, stop_price, tp_price = calculate_position_size(
                    equity=m2m_equity,
                    entry_price=current_close,
                    risk_pct=risk_pct,
                    stop_bps=stop_bps,
                    tp_r=tp_r,
                    max_leverage=max_leverage,
                    is_long=True,
                )
                
                if qty is None:
                    equity_history.append({"ts": current_candle.ts, "equity": float(realized_equity)})
                    continue
                
                entry_price_slipped = apply_slippage(current_close, True, True)
                entry_fees = calculate_fees(entry_price_slipped * qty)
                
                position = "LONG"
                entry_price = entry_price_slipped
                entry_ts = current_candle.ts
                position_quantity = qty
                realized_equity -= entry_fees
                total_fees += entry_fees
            elif signal == "SELL":
                qty, stop_price, tp_price = calculate_position_size(
                    equity=m2m_equity,
                    entry_price=current_close,
                    risk_pct=risk_pct,
                    stop_bps=stop_bps,
                    tp_r=tp_r,
                    max_leverage=max_leverage,
                    is_long=False,
                )
                
                if qty is None:
                    equity_history.append({"ts": current_candle.ts, "equity": float(realized_equity)})
                    continue
                
                entry_price_slipped = apply_slippage(current_close, True, False)
                entry_fees = calculate_fees(entry_price_slipped * qty)
                
                position = "SHORT"
                entry_price = entry_price_slipped
                entry_ts = current_candle.ts
                position_quantity = qty
                realized_equity -= entry_fees
                total_fees += entry_fees
        else:
            # Check for stop/tp hits
            exit_reason = None
            exit_price = None
            
            if position == "LONG":
                stop_hit = current_low <= stop_price
                tp_hit = current_high >= tp_price
                
                if stop_hit and tp_hit:
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
            else:
                stop_hit = current_high >= stop_price
                tp_hit = current_low <= tp_price
                
                if stop_hit and tp_hit:
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
            
            if exit_reason is not None:
                exit_price_slipped = apply_slippage(exit_price, False, position == "LONG")
                
                if position == "LONG":
                    pnl = (exit_price_slipped - entry_price) * position_quantity
                else:
                    pnl = (entry_price - exit_price_slipped) * position_quantity
                
                exit_fees = calculate_fees(exit_price_slipped * position_quantity)
                
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
                
                if pnl - exit_fees >= 0:
                    wins += 1
                else:
                    losses += 1
                
                realized_equity += pnl - exit_fees
                total_fees += exit_fees
                position = None
            elif (position == "LONG" and signal == "SELL") or (position == "SHORT" and signal == "BUY"):
                # Crossover reversal
                exit_price_slipped = apply_slippage(current_close, False, position == "LONG")
                
                if position == "LONG":
                    pnl = (exit_price_slipped - entry_price) * position_quantity
                else:
                    pnl = (entry_price - exit_price_slipped) * position_quantity
                
                exit_fees = calculate_fees(exit_price_slipped * position_quantity)
                
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
                
                if pnl - exit_fees >= 0:
                    wins += 1
                else:
                    losses += 1
                
                realized_equity += pnl - exit_fees
                total_fees += exit_fees
                position = None
        
        equity_history.append({"ts": current_candle.ts, "equity": float(realized_equity)})
        
        # Track max drawdown
        max_equity = max(max_equity, realized_equity)
        current_drawdown = (max_equity - realized_equity) / max_equity if max_equity > 0 else 0
        max_drawdown = max(max_drawdown, current_drawdown)
    
    # Final equity
    equity = realized_equity
    net_pnl = equity - starting_balance
    
    return {
        "net_pnl": float(net_pnl),
        "max_drawdown": float(max_drawdown),
        "trades": len(trades),
        "wins": wins,
        "losses": losses,
        "fees_total": float(total_fees),
        "equity_history": equity_history,
        "trades_list": trades,
    }


def run_validation(
    candles: List[Candle],
    starting_balance: float,
    fees_bps: float,
    slip_bps: float,
    risk_pct: float,
    max_leverage: float,
    intrabar_mode: str,
    grid_str: str,
    validate_splits: int,
    validate_train: int,
    validate_test: int,
    max_candidates: int = 200,
) -> Dict[str, Any]:
    """
    Run walk-forward validation with parameter grid sweep.
    Returns comprehensive validation results including leaderboard and best parameters.
    """
    # Parse grid with candidate limit
    param_combinations = parse_grid(grid_str, max_candidates=max_candidates)
    
    # Normalize candles
    candles = normalize_candle_order(candles)
    
    # Calculate minimum candles required for walk-forward validation
    # For split i: train = candles[i*test : i*test + train], test = candles[i*test + train : i*test + train + test]
    # Therefore minimum candles needed = train + splits*test
    total_candles = len(candles)
    required_candles = validate_train + validate_splits * validate_test
    
    # Auto-bump if needed
    if total_candles < required_candles:
        raise ValueError(
            f"Insufficient candles for validation. Need at least {required_candles} candles "
            f"(train={validate_train} + splits={validate_splits}*test={validate_test}), "
            f"but only have {total_candles} candles. "
            f"Increase --limit or reduce validation parameters."
        )
    
    # Ensure we have enough candles for the largest SMA window in the grid
    max_sma_window = 0
    for params in param_combinations:
        max_sma_window = max(max_sma_window, params["fast_sma"], params["slow_sma"])
    
    if validate_train < max_sma_window + 1:
        raise ValueError(
            f"Train window ({validate_train}) too small for largest SMA window ({max_sma_window}). "
            f"Need at least {max_sma_window + 1} candles for training."
        )
    
    # Walk-forward splits
    folds = []
    all_train_results = []  # Collect all training results for leaderboard
    
    for k in range(validate_splits):
        train_start = k * validate_test  # Rolling window: train starts after previous test
        train_end = train_start + validate_train
        test_end = train_end + validate_test
        
        # Ensure we don't go beyond available candles
        if train_end > total_candles or test_end > total_candles:
            break
        
        train_candles = candles[train_start:train_end]
        test_candles = candles[train_end:test_end]
        
        # Find best params on train
        best_params = None
        best_objective = -float('inf')
        train_results = []
        successful_candidates = 0
        
        for params in param_combinations:
            try:
                result = run_backtest_on_segment(
                    candles=train_candles,
                    starting_balance=starting_balance,
                    fees_bps=fees_bps,
                    slip_bps=slip_bps,
                    risk_pct=risk_pct,
                    fast_sma=params["fast_sma"],
                    slow_sma=params["slow_sma"],
                    stop_bps=params["stop_bps"],
                    tp_r=params["tp_r"],
                    max_leverage=max_leverage,
                    intrabar_mode=intrabar_mode,
                )
                
                # Calculate objective: net_pnl - 0.5 * max_drawdown * starting_balance
                objective = result["net_pnl"] - 0.5 * result["max_drawdown"] * starting_balance
                
                train_results.append({
                    **params,
                    **result,
                    "objective": objective,
                    "fold_index": k,
                })
                all_train_results.append(train_results[-1])
                
                if objective > best_objective:
                    best_objective = objective
                    best_params = params
                
                successful_candidates += 1
                
            except Exception as e:
                # Log failed candidate but continue
                append_event({
                    "event": "ValidationCandidateFailed",
                    "fold": k,
                    "params": params,
                    "error": str(e)
                })
        
        # If no candidates succeeded, raise clear error
        if successful_candidates == 0:
            raise ValueError(
                f"0 candidates evaluated successfully in fold {k}. "
                f"All {len(param_combinations)} parameter combinations failed. "
                f"Check your grid parameters and candle data quality."
            )
        
        # If best_params is still None (shouldn't happen if successful_candidates > 0), use first params
        if best_params is None:
            best_params = param_combinations[0]
            append_event({
                "event": "ValidationFallbackParams",
                "fold": k,
                "reason": "best_params was None despite successful candidates",
                "params": best_params
            })
        
        # Run test with best params
        test_result = run_backtest_on_segment(
            candles=test_candles,
            starting_balance=starting_balance,
            fees_bps=fees_bps,
            slip_bps=slip_bps,
            risk_pct=risk_pct,
            fast_sma=best_params["fast_sma"],
            slow_sma=best_params["slow_sma"],
            stop_bps=best_params["stop_bps"],
            tp_r=best_params["tp_r"],
            max_leverage=max_leverage,
            intrabar_mode=intrabar_mode,
        )
        
        folds.append({
            "fold_index": k,
            "train_start": train_candles[0].ts if train_candles else "N/A",
            "train_end": train_candles[-1].ts if train_candles else "N/A",
            "test_start": test_candles[0].ts if test_candles else "N/A",
            "test_end": test_candles[-1].ts if test_candles else "N/A",
            "best_params": best_params,
            "best_objective": best_objective,
            "test_result": test_result,
            "train_results": train_results,
        })
    
    # Aggregate results
    total_os_pnl = sum(fold["test_result"]["net_pnl"] for fold in folds)
    avg_os_pnl = total_os_pnl / len(folds) if folds else 0.0
    worst_os_pnl = min(fold["test_result"]["net_pnl"] for fold in folds) if folds else 0.0
    avg_max_dd = sum(fold["test_result"]["max_drawdown"] for fold in folds) / len(folds) if folds else 0.0
    total_trades = sum(fold["test_result"]["trades"] for fold in folds)
    
    # Calculate win rate and other stats
    all_trades = []
    for fold in folds:
        all_trades.extend(fold["test_result"]["trades_list"])
    
    wins = sum(1 for t in all_trades if t["pnl"] >= 0)
    losses = sum(1 for t in all_trades if t["pnl"] < 0)
    win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0.0
    
    # Calculate profit factor and expectancy
    winning_trades = [t for t in all_trades if t["pnl"] >= 0]
    losing_trades = [t for t in all_trades if t["pnl"] < 0]
    avg_win = sum(t["pnl"] for t in winning_trades) / len(winning_trades) if winning_trades else 0.0
    avg_loss = sum(t["pnl"] for t in losing_trades) / len(losing_trades) if losing_trades else 0.0
    profit_factor = (sum(t["pnl"] for t in winning_trades) / abs(sum(t["pnl"] for t in losing_trades))) if losing_trades else float('inf')
    expectancy = (avg_win * win_rate) + (avg_loss * (1 - win_rate)) if (wins + losses) > 0 else 0.0
    
    # Count parameter frequency
    param_freq = {}
    for fold in folds:
        params = fold["best_params"]
        key = f"sma{params['fast_sma']},{params['slow_sma']}_stop{params['stop_bps']}_tp{params['tp_r']}"
        param_freq[key] = param_freq.get(key, 0) + 1
    
    # Create leaderboard from all training results
    # Sort by objective (descending)
    leaderboard = sorted(all_train_results, key=lambda x: x["objective"], reverse=True)[:10]
    
    # Find best overall parameters (highest average objective across folds)
    best_params_overall = None
    best_avg_objective = -float('inf')
    
    # Group by parameters to find best average performer
    params_performance = {}
    for result in all_train_results:
        param_key = f"{result['fast_sma']},{result['slow_sma']},{result['stop_bps']},{result['tp_r']}"
        if param_key not in params_performance:
            params_performance[param_key] = {
                'count': 0,
                'total_objective': 0.0,
                'params': {
                    'fast_sma': result['fast_sma'],
                    'slow_sma': result['slow_sma'],
                    'stop_bps': result['stop_bps'],
                    'tp_r': result['tp_r']
                }
            }
        params_performance[param_key]['count'] += 1
        params_performance[param_key]['total_objective'] += result['objective']
    
    # Find best average performer
    for param_key, perf in params_performance.items():
        avg_obj = perf['total_objective'] / perf['count']
        if avg_obj > best_avg_objective:
            best_avg_objective = avg_obj
            best_params_overall = perf['params']
    
    # Stitch equity curves
    equity_history = []
    current_equity = starting_balance
    for fold in folds:
        for point in fold["test_result"]["equity_history"]:
            current_equity = point["equity"]
            equity_history.append({"ts": point["ts"], "equity": current_equity})
    
    # Create validation report
    validation_report = {
        "requested_params": {
            "splits": validate_splits,
            "train": validate_train,
            "test": validate_test,
            "grid": grid_str,
            "max_candidates": max_candidates
        },
        "candle_requirements": {
            "required": required_candles,
            "actual": total_candles,
            "formula": f"train({validate_train}) + splits({validate_splits})*test({validate_test})"
        },
        "grid_parsed": {
            "total_combinations": len(param_combinations),
            "combinations": param_combinations
        },
        "leaderboard": leaderboard,
        "best_params": best_params_overall,
        "best_metrics": {
            "avg_objective": best_avg_objective,
            "total_os_pnl": total_os_pnl,
            "avg_os_pnl": avg_os_pnl,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "expectancy": expectancy
        }
    }
    
    return {
        "folds": folds,
        "total_os_pnl": total_os_pnl,
        "avg_os_pnl": avg_os_pnl,
        "worst_os_pnl": worst_os_pnl,
        "avg_max_dd": avg_max_dd,
        "total_trades": total_trades,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "param_freq": param_freq,
        "equity_history": equity_history,
        "all_trades": all_trades,
        "splits_used": len(folds),
        "validation_report": validation_report,
        "leaderboard": leaderboard,
        "best_params_overall": best_params_overall
    }


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
                    is_long=True,
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
                    is_long=False,
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
                    is_long=True,
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
                    is_long=False,
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
                    is_long=(position.get("side") == "LONG"),
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
                        is_long=True,
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
                        is_long=False,
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
    
    # Validation mode section (if available)
    validation_section = ""
    validation_json_path = LATEST_DIR / "validation.json"
    if validation_json_path.exists():
        try:
            with validation_json_path.open("r", encoding="utf-8") as f:
                validate_data = json.load(f)
            
            # Top cards with best parameters
            best_params = validate_data.get('best_params', {})
            best_params_card = ""
            if best_params:
                best_params_card = f"""
    <div class="card">
        <div class="card-label">Best Parameters</div>
        <div class="card-value" style="font-size: 0.9em;">
            SMA: {best_params.get('fast_sma', 'N/A')},{best_params.get('slow_sma', 'N/A')}<br>
            Stop: {best_params.get('stop_bps', 'N/A')} bps<br>
            TP: {best_params.get('tp_r', 'N/A')}
        </div>
    </div>
"""
            
            # Leaderboard table (top 10)
            leaderboard_rows = ""
            for entry in validate_data.get('leaderboard', [])[:10]:
                leaderboard_rows += f"""
    <tr>
        <td>{entry.get('rank', 'N/A')}</td>
        <td>{entry.get('fast_sma', 'N/A')},{entry.get('slow_sma', 'N/A')}</td>
        <td>{entry.get('stop_bps', 'N/A')}</td>
        <td>{entry.get('tp_r', 'N/A')}</td>
        <td>${entry.get('net_pnl', 0):.2f}</td>
        <td>{entry.get('max_drawdown', 0):.2%}</td>
        <td>{entry.get('win_rate', 0):.2%}</td>
        <td>{entry.get('trades', 0)}</td>
        <td>${entry.get('fees_total', 0):.2f}</td>
        <td>{entry.get('objective', 0):.2f}</td>
    </tr>
"""
            
            # Main validation section
            validation_section = f"""
    <div class="section">
        <h2>Validation Results</h2>
        <div class="cards">
            <div class="card">
                <div class="card-label">Out-of-Sample Net PnL</div>
                <div class="card-value">${validate_data.get('total_os_pnl', 0):.2f}</div>
            </div>
            <div class="card">
                <div class="card-label">Avg Fold PnL</div>
                <div class="card-value">${validate_data.get('avg_os_pnl', 0):.2f}</div>
            </div>
            <div class="card">
                <div class="card-label">Win Rate</div>
                <div class="card-value">{validate_data.get('win_rate', 0):.2%}</div>
            </div>
            <div class="card">
                <div class="card-label">Profit Factor</div>
                <div class="card-value">{validate_data.get('profit_factor', 0):.2f}</div>
            </div>
            {best_params_card}
            <div class="card">
                <div class="card-label">Candles Required</div>
                <div class="card-value" style="font-size: 0.9em;">
                    {validate_data.get('candle_requirements', {}).get('required', 'N/A')} required<br>
                    {validate_data.get('candle_requirements', {}).get('actual', 'N/A')} actual
                </div>
            </div>
            <div class="card">
                <div class="card-label">Grid Combinations</div>
                <div class="card-value" style="font-size: 0.9em;">
                    {validate_data.get('grid_parsed', {}).get('total_combinations', 0)} total<br>
                    Top 10 shown
                </div>
            </div>
        </div>
        
        <h3 style="margin-top: 30px;">Leaderboard (Top 10)</h3>
        <table>
            <thead>
                <tr>
                    <th>Rank</th>
                    <th>SMA</th>
                    <th>Stop (bps)</th>
                    <th>TP Ratio</th>
                    <th>Net PnL</th>
                    <th>Max DD</th>
                    <th>Win Rate</th>
                    <th>Trades</th>
                    <th>Fees</th>
                    <th>Objective</th>
                </tr>
            </thead>
            <tbody>{leaderboard_rows}</tbody>
        </table>
    </div>
"""
        except Exception as e:
            append_event({"event": "ValidationRenderError", "message": str(e)})

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
  {validation_section}
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
    ap.add_argument("--mode", choices=["single", "backtest", "live", "validate", "selftest", "orchestrated"], default=None,
                   help="Run mode: single (default), backtest, live paper trading, validate, selftest, or orchestrated")
    ap.add_argument("--once", action="store_true", default=False,
                   help="Run once and exit (for orchestrated mode)")
    ap.add_argument("--risk-pct", type=float, default=1.0, help="% equity risked per trade")
    ap.add_argument("--stop-bps", type=float, default=30.0, help="stop distance in bps from entry (0.30%)")
    ap.add_argument("--tp-r", type=float, default=1.5, help="take profit = stop_distance * tp-r")
    ap.add_argument("--max-leverage", type=float, default=1.0, help="cap notional: qty*entry <= equity*max_leverage")
    ap.add_argument("--intrabar-mode", choices=["conservative", "optimistic"], default="conservative",
                   help="conservative: stop first; optimistic: tp first")
    ap.add_argument("--validate-splits", type=int, default=5, help="number of walk-forward folds")
    ap.add_argument("--validate-train", type=int, default=600, help="candles used for train window")
    ap.add_argument("--validate-test", type=int, default=200, help="candles used for test window")
    ap.add_argument("--grid", type=str, default="sma=10,30;stop=20,30,40;tp=1.0,1.5,2.0",
                   help="parameter grid: sma=fast,slow;stop=...;tp=...")
    ap.add_argument("--validate-max-candidates", type=int, default=200,
                   help="maximum number of parameter combinations to evaluate in validation mode")
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

        if mode == "validate":
            # Validation mode
            append_event({"event": "ValidationStarted", "splits": args.validate_splits,
                         "train": args.validate_train, "test": args.validate_test, "grid": args.grid})
            
            # Calculate total candles needed for validation
            total_candles_needed = args.validate_splits * (args.validate_train + args.validate_test)
            
            # Use paging for Bitunix to fetch enough candles
            if args.source == "bitunix":
                # Use paging to fetch enough candles for validation
                candles = []
                try:
                    Provider = _get_bitunix_provider_class()
                    client = Provider(symbol=args.symbol)
                    candles = client.klines_paged(interval=args.interval, total=total_candles_needed)
                    append_event({"event": "BitunixPagedCandlesLoaded", "requested": total_candles_needed, "loaded": len(candles)})
                except Exception as e:
                    append_event({"event": "BitunixPagingFailed", "error": str(e)})
                    # Fallback to regular loading with higher limit
                    limit = min(max(total_candles_needed, 2000), 5000)  # Cap at 5000 for safety
                    candles = load_bitunix_candles(args.symbol, args.interval, limit)
            else:
                # For mock data, generate enough candles
                candles = load_mock_candles(total_candles_needed)
            
            append_event({"event": "MarketDataLoaded", "source": args.source, "symbol": args.symbol, "interval": args.interval, "count": len(candles)})
            
            # Normalize candle order
            candles = normalize_candle_order(candles)
            
            # Run validation
            validation_result = run_validation(
                candles=candles,
                starting_balance=starting_balance,
                fees_bps=float(args.fees_bps),
                slip_bps=float(args.slip_bps),
                risk_pct=float(args.risk_pct),
                max_leverage=float(args.max_leverage),
                intrabar_mode=args.intrabar_mode,
                grid_str=args.grid,
                validate_splits=args.validate_splits,
                validate_train=args.validate_train,
                validate_test=args.validate_test,
                max_candidates=args.validate_max_candidates,
            )
            
            # Write validation outputs
            trades = validation_result["all_trades"]
            ending_balance = starting_balance + validation_result["total_os_pnl"]
            
            # Write validation.json with comprehensive report
            validation_json_path = LATEST_DIR / "validation.json"
            temp_validation = validation_json_path.with_suffix(".tmp")
            try:
                validation_json_content = {
                    "meta": {
                        "timestamp": utc_ts(),
                        "mode": "validate",
                        "source": args.source,
                        "symbol": args.symbol,
                        "interval": args.interval
                    },
                    **validation_result["validation_report"]
                }
                
                # Add leaderboard details
                leaderboard_details = []
                for i, entry in enumerate(validation_result["leaderboard"]):
                    leaderboard_details.append({
                        "rank": i + 1,
                        "fast_sma": entry["fast_sma"],
                        "slow_sma": entry["slow_sma"],
                        "stop_bps": entry["stop_bps"],
                        "tp_r": entry["tp_r"],
                        "net_pnl": entry["net_pnl"],
                        "max_drawdown": entry["max_drawdown"],
                        "win_rate": entry.get("win_rate", 0),
                        "trades": entry["trades"],
                        "fees_total": entry["fees_total"],
                        "objective": entry["objective"]
                    })
                validation_json_content["leaderboard"] = leaderboard_details
                
                # Add best params details
                if validation_result["best_params_overall"]:
                    best_params = validation_result["best_params_overall"]
                    validation_json_content["best_params"] = {
                        "fast_sma": best_params["fast_sma"],
                        "slow_sma": best_params["slow_sma"],
                        "stop_bps": best_params["stop_bps"],
                        "tp_r": best_params["tp_r"],
                        **validation_result.get("best_metrics", {})
                    }
                
                with temp_validation.open("w", encoding="utf-8") as f:
                    json.dump(validation_json_content, f, indent=2)
                temp_validation.replace(validation_json_path)
                append_event({"event": "ValidationJSONWritten", "path": str(validation_json_path)})
            except Exception as e:
                if temp_validation.exists():
                    temp_validation.unlink()
                raise RuntimeError(f"Failed to write validation.json: {e}")
            
            # Also write the full results for backward compatibility
            validate_results_path = LATEST_DIR / "validate_results.json"
            temp_results = validate_results_path.with_suffix(".tmp")
            try:
                with temp_results.open("w", encoding="utf-8") as f:
                    json.dump(validation_result, f, indent=2)
                temp_results.replace(validate_results_path)
            except Exception as e:
                if temp_results.exists():
                    temp_results.unlink()
                raise RuntimeError(f"Failed to write validate_results.json: {e}")
            
            # Write validate_folds.csv
            validate_folds_path = LATEST_DIR / "validate_folds.csv"
            temp_folds = validate_folds_path.with_suffix(".tmp")
            try:
                with temp_folds.open("w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=[
                        "fold_index", "train_start", "train_end", "test_start", "test_end",
                        "fast_sma", "slow_sma", "stop_bps", "tp_r",
                        "test_net_pnl", "test_max_drawdown", "test_trades", "test_win_rate"
                    ])
                    writer.writeheader()
                    for fold in validation_result["folds"]:
                        bp = fold["best_params"]
                        tr = fold["test_result"]
                        wins = tr["wins"]
                        losses = tr["losses"]
                        win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0.0
                        writer.writerow({
                            "fold_index": fold["fold_index"],
                            "train_start": fold["train_start"],
                            "train_end": fold["train_end"],
                            "test_start": fold["test_start"],
                            "test_end": fold["test_end"],
                            "fast_sma": bp["fast_sma"],
                            "slow_sma": bp["slow_sma"],
                            "stop_bps": bp["stop_bps"],
                            "tp_r": bp["tp_r"],
                            "test_net_pnl": tr["net_pnl"],
                            "test_max_drawdown": tr["max_drawdown"],
                            "test_trades": tr["trades"],
                            "test_win_rate": win_rate,
                        })
                temp_folds.replace(validate_folds_path)
            except Exception as e:
                if temp_folds.exists():
                    temp_folds.unlink()
                raise RuntimeError(f"Failed to write validate_folds.csv: {e}")
            
            # Write equity.csv
            equity_csv_path = LATEST_DIR / "equity.csv"
            temp_equity = equity_csv_path.with_suffix(".tmp")
            try:
                with temp_equity.open("w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=["ts", "equity"])
                    writer.writeheader()
                    for eq in validation_result["equity_history"]:
                        writer.writerow(eq)
                temp_equity.replace(equity_csv_path)
            except Exception as e:
                if temp_equity.exists():
                    temp_equity.unlink()
                raise RuntimeError(f"Failed to write equity.csv: {e}")
            
            append_event({"event": "ValidationFinished", "folds": len(validation_result["folds"]),
                         "total_os_pnl": validation_result["total_os_pnl"]})
        elif mode == "live":
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
            
        elif mode == "selftest":
            # Self-test mode
            append_event({"event": "SelfTestStarted", "intrabar_mode": args.intrabar_mode})
            
            # Run selftest
            success, message = run_selftest(intrabar_mode=args.intrabar_mode)
            
            # Create a summary with selftest results
            last_candle = candles[-1] if candles else Candle(ts="selftest", open=100.0, high=100.0, low=100.0, close=100.0, volume=1.0)
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
                "ending_balance": starting_balance,
                "net_pnl": 0.0,
                "trades": 0,
                "mode": mode,
                "selftest_result": "PASS" if success else "FAIL",
                "selftest_message": message,
            }
            
            # Write trades.csv (empty for selftest)
            write_trades_csv([])
            
            # Write state.json with selftest info
            write_state({
                "summary": summary,
                "selftest": {
                    "success": success,
                    "message": message,
                    "timestamp": utc_ts()
                }
            })
            
            # Render HTML with selftest results
            error_message = "" if success else f"SELFTEST FAILED: {message}"
            render_html(summary, [], error_message)
            
            append_event({"event": "SelfTestFinished", "success": success, "message": message})
            
            if success:
                print(f"SELFTEST PASS: {message}")
                return 0
            else:
                print(f"SELFTEST FAIL: {message}", file=sys.stderr)
                return 1

        elif mode == "orchestrated":
            # Orchestrated mode - end-to-end with artifact validation
            # Run orchestrated mode (bitunix public API doesn't require credentials)
            success, message = run_orchestrated_mode(
                symbol=args.symbol,
                interval=args.interval,
                source=args.source,
                limit=args.limit,
                fees_bps=float(args.fees_bps),
                slip_bps=float(args.slip_bps),
            )
            
            if success:
                print(message)
                return 0
            else:
                print(f"ERROR: {message}", file=sys.stderr)
                return 1

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


def run_selftest(intrabar_mode: str = "conservative") -> tuple[bool, str]:
    """
    Run deterministic self-test to verify risk engine correctness.
    Tests LONG TP, LONG STOP, SHORT TP, SHORT STOP, and intrabar ambiguity.
    Returns (success, message)
    """
    # Create deterministic candle sequence that triggers specific scenarios
    # Need at least 31 candles for backtest (30 for SMA + 1 for trading)
    candles = []
    price = 100.0
    for i in range(50):  # Generate 50 candles to ensure we have enough
        # Create price movement that will trigger both LONG and SHORT scenarios
        if i < 25:
            # Upward trend for LONG positions
            price += 0.5
        else:
            # Downward trend for SHORT positions
            price -= 0.5
        
        # Add some volatility
        high = price + 2.0
        low = price - 2.0
        close = price + (0.5 if i % 2 == 0 else -0.5)  # Some variability
        
        candles.append(Candle(ts=f"test_{i:04d}", open=price, high=high, low=low, close=close, volume=1.0))
    
    # Test parameters
    starting_balance = 10000.0
    fees_bps = 0.0  # No fees for simpler testing
    slip_bps = 0.0  # No slippage for simpler testing
    risk_pct = 1.0
    stop_bps = 50.0  # 0.5% stop
    tp_r = 2.0  # 2:1 reward:risk
    max_leverage = 1.0
    
    # Run backtest in position mode
    try:
        result = run_backtest_position_mode(
            candles=candles,
            starting_balance=starting_balance,
            fees_bps=fees_bps,
            slip_bps=slip_bps,
            risk_pct=risk_pct,
            stop_bps=stop_bps,
            tp_r=tp_r,
            max_leverage=max_leverage,
            intrabar_mode=intrabar_mode,
        )
        
        trades = result["trades"]
        
        # Verify we have trades
        if len(trades) == 0:
            return False, "No trades generated in selftest"
        
        # Check that all trades have valid exit reasons
        valid_reasons = {"STOP", "TP", "REVERSE", "EOD"}
        for trade in trades:
            if trade["exit_reason"] not in valid_reasons:
                return False, f"Invalid exit reason: {trade['exit_reason']}"
        
        # Verify stop/tp ordering for each trade
        for trade in trades:
            side = trade["side"]
            entry = trade["entry"]
            stop = trade["stop_price"]
            tp = trade["tp_price"]
            
            if side == "LONG":
                if not (stop < entry < tp):
                    return False, f"LONG trade ordering violation: stop={stop:.2f}, entry={entry:.2f}, tp={tp:.2f}"
            else:  # SHORT
                if not (tp < entry < stop):
                    return False, f"SHORT trade ordering violation: tp={tp:.2f}, entry={entry:.2f}, stop={stop:.2f}"
        
        # Verify PnL calculation correctness
        for trade in trades:
            side = trade["side"]
            entry = trade["entry"]
            exit_price = trade["exit"]
            qty = trade["quantity"]
            fees = trade["fees"]
            pnl = trade["pnl"]
            
            # Calculate expected PnL
            if side == "LONG":
                expected_gross = (exit_price - entry) * qty
            else:  # SHORT
                expected_gross = (entry - exit_price) * qty
            
            expected_pnl = expected_gross - fees
            
            # Allow small floating point differences
            if abs(pnl - expected_pnl) > 0.01:
                return False, f"PnL calculation error: expected={expected_pnl:.2f}, actual={pnl:.2f}"
        
        return True, f"All tests passed. Generated {len(trades)} trades with correct ordering and PnL calculations."
        
    except Exception as e:
        return False, f"Selftest failed with exception: {str(e)}"


if __name__ == "__main__":
    raise SystemExit(main())
