"""
Live Trading Execution Engine.
Phase C refactoring: Extracted from run.py.
"""

from __future__ import annotations

import csv
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Callable

from laptop_agents.core.logger import logger
from laptop_agents.core import hard_limits
from laptop_agents.trading.helpers import (
    Candle,
    utc_ts,
    calculate_position_size,
)


def calculate_fees(notional: float, fees_bps: float) -> float:
    """Helper function to calculate fees."""
    return notional * (fees_bps / 10_000.0)


def apply_slippage(
    price: float, is_entry: bool, is_long: bool, slip_bps: float
) -> float:
    """Helper function to apply slippage."""
    slip_rate = slip_bps / 10_000.0
    if is_long:
        return price * (1.0 + slip_rate) if is_entry else price * (1.0 - slip_rate)
    else:
        return price * (1.0 - slip_rate) if is_entry else price * (1.0 + slip_rate)


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
    paper_dir: Path | None = None,
    append_event_fn: Callable | None = None,
) -> tuple[List[Dict[str, Any]], float, Dict[str, Any]]:
    """
    Run live paper trading with persistent state and risk management.
    Returns (trades, ending_balance, state)
    """
    if paper_dir is None:
        # Fallback to a default if not provided, though orchestrator should provide it
        paper_dir = Path("paper")

    def _append_event(obj: Dict[str, Any]):
        if append_event_fn:
            append_event_fn(obj, paper=True)
        else:
            # Fallback simple logging if no callback provided
            obj.setdefault("timestamp", utc_ts())
            logger.info(f"EVENT: {obj.get('event', 'UnnamedEvent')}", obj)
            paper_dir.mkdir(exist_ok=True)
            with (paper_dir / "events.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    # Enforce hard limits on parameters
    actual_max_leverage = min(max_leverage, getattr(hard_limits, "MAX_LEVERAGE", 20.0))
    if actual_max_leverage != max_leverage:
        _append_event(
            {
                "event": "HardLimitLeverageCapped",
                "requested": max_leverage,
                "capped": actual_max_leverage,
            }
        )
        max_leverage = actual_max_leverage

    actual_tp_r = max(tp_r, getattr(hard_limits, "MIN_RR_RATIO", 1.0))
    if actual_tp_r != tp_r:
        _append_event(
            {"event": "HardLimitRRCapped", "requested": tp_r, "capped": actual_tp_r}
        )
        tp_r = actual_tp_r

    # Load or initialize state
    state_path = paper_dir / "state.json"
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
    paper_dir.mkdir(exist_ok=True)

    # Check for Daily Loss Limit
    max_daily_loss = getattr(hard_limits, "MAX_DAILY_LOSS_USD", 50.0)
    if state.get("realized_pnl", 0.0) <= -max_daily_loss:
        _append_event(
            {
                "event": "HardLimitDailyLossReached",
                "pnl": state["realized_pnl"],
                "limit": max_daily_loss,
            }
        )
        return [], state["equity"], state

    # Identify new candles
    last_ts = state.get("last_ts")
    new_candles = []
    for candle in candles:
        if last_ts is None or candle.ts > last_ts:
            new_candles.append(candle)

    if not new_candles:
        _append_event({"event": "NoNewCandles", "last_ts": last_ts})
        return [], state["equity"], state

    # Process new candles
    trades = []
    for candle in new_candles:
        current_close = float(candle.close)
        current_high = float(candle.high)
        current_low = float(candle.low)

        from laptop_agents.trading.signal import generate_signal

        candles_subset = [c for c in candles if c.ts <= candle.ts]
        signal = generate_signal(candles_subset)

        if signal is None:
            # Update state with no position change
            state["last_ts"] = candle.ts
            continue

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
                    _append_event(
                        {
                            "event": "RiskSizingSkipped",
                            "reason": "invalid stop distance or qty",
                        }
                    )
                    continue

                # Enforce MAX_POSITION_SIZE_USD
                max_notional_usd = getattr(
                    hard_limits, "MAX_POSITION_SIZE_USD", 200000.0
                )
                if qty * current_close > max_notional_usd:
                    new_qty = max_notional_usd / current_close
                    _append_event(
                        {
                            "event": "HardLimitPositionCapped",
                            "original_qty": qty,
                            "capped_qty": new_qty,
                            "limit": max_notional_usd,
                        }
                    )
                    qty = new_qty

                entry_price_slipped = apply_slippage(
                    current_close, True, True, slip_bps
                )
                entry_fees = calculate_fees(entry_price_slipped * qty, fees_bps)

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

                _append_event(
                    {
                        "event": "PositionOpened",
                        "side": "LONG",
                        "ts": candle.ts,
                        "price": entry_price_slipped,
                        "quantity": qty,
                        "stop": stop_price,
                        "tp": tp_price,
                    }
                )
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
                    _append_event(
                        {
                            "event": "RiskSizingSkipped",
                            "reason": "invalid stop distance or qty",
                        }
                    )
                    continue

                # Enforce MAX_POSITION_SIZE_USD
                max_notional_usd = getattr(
                    hard_limits, "MAX_POSITION_SIZE_USD", 200000.0
                )
                if qty * current_close > max_notional_usd:
                    new_qty = max_notional_usd / current_close
                    _append_event(
                        {
                            "event": "HardLimitPositionCapped",
                            "original_qty": qty,
                            "capped_qty": new_qty,
                            "limit": max_notional_usd,
                        }
                    )
                    qty = new_qty

                entry_price_slipped = apply_slippage(
                    current_close, True, False, slip_bps
                )
                entry_fees = calculate_fees(entry_price_slipped * qty, fees_bps)

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

                _append_event(
                    {
                        "event": "PositionOpened",
                        "side": "SHORT",
                        "ts": candle.ts,
                        "price": entry_price_slipped,
                        "quantity": qty,
                        "stop": stop_price,
                        "tp": tp_price,
                    }
                )
        else:
            # Check for stop/tp hits
            exit_reason: str | None = None
            exit_price: float = 0.0

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
                exit_price_slipped = apply_slippage(
                    exit_price, False, position["side"] == "LONG", slip_bps
                )

                if position["side"] == "LONG":
                    pnl = (exit_price_slipped - position["entry_price"]) * position[
                        "quantity"
                    ]
                else:
                    pnl = (position["entry_price"] - exit_price_slipped) * position[
                        "quantity"
                    ]

                exit_fees = calculate_fees(
                    exit_price_slipped * position["quantity"], fees_bps
                )

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
                state["realized_pnl"] = state.get("realized_pnl", 0.0) + (
                    pnl - exit_fees
                )
                state["position"] = None

                _append_event(
                    {
                        "event": "PositionClosed",
                        "side": position["side"],
                        "ts": candle.ts,
                        "price": exit_price_slipped,
                        "pnl": pnl - exit_fees,
                        "reason": exit_reason,
                    }
                )
            elif (position["side"] == "LONG" and signal == "SELL") or (
                position["side"] == "SHORT" and signal == "BUY"
            ):
                # Crossover reversal - close at current close
                exit_price_slipped = apply_slippage(
                    current_close, False, position["side"] == "LONG", slip_bps
                )

                if position["side"] == "LONG":
                    pnl = (exit_price_slipped - position["entry_price"]) * position[
                        "quantity"
                    ]
                else:
                    pnl = (position["entry_price"] - exit_price_slipped) * position[
                        "quantity"
                    ]

                exit_fees = calculate_fees(
                    exit_price_slipped * position["quantity"], fees_bps
                )

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
                state["realized_pnl"] = state.get("realized_pnl", 0.0) + (
                    pnl - exit_fees
                )
                state["position"] = None

                _append_event(
                    {
                        "event": "PositionClosed",
                        "side": position["side"],
                        "ts": candle.ts,
                        "price": exit_price_slipped,
                        "pnl": pnl - exit_fees,
                        "reason": "REVERSE",
                    }
                )

                # Check for Daily Loss Limit after a closure
                if state.get("realized_pnl", 0.0) <= -max_daily_loss:
                    _append_event(
                        {
                            "event": "HardLimitDailyLossReached",
                            "pnl": state["realized_pnl"],
                            "limit": max_daily_loss,
                        }
                    )
                    # Skip opening new position if limit reached
                else:
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
                            _append_event(
                                {
                                    "event": "RiskSizingSkipped",
                                    "reason": "invalid stop distance or qty",
                                }
                            )
                            continue

                        # Enforce MAX_POSITION_SIZE_USD
                        max_notional_usd = getattr(
                            hard_limits, "MAX_POSITION_SIZE_USD", 200000.0
                        )
                        if qty * current_close > max_notional_usd:
                            new_qty = max_notional_usd / current_close
                            _append_event(
                                {
                                    "event": "HardLimitPositionCapped",
                                    "original_qty": qty,
                                    "capped_qty": new_qty,
                                    "limit": max_notional_usd,
                                }
                            )
                            qty = new_qty

                        entry_price_slipped = apply_slippage(
                            current_close, True, True, slip_bps
                        )
                        entry_fees = calculate_fees(entry_price_slipped * qty, fees_bps)

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

                        _append_event(
                            {
                                "event": "PositionOpened",
                                "side": "LONG",
                                "ts": candle.ts,
                                "price": entry_price_slipped,
                                "quantity": qty,
                                "stop": stop_price,
                                "tp": tp_price,
                            }
                        )
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
                            _append_event(
                                {
                                    "event": "RiskSizingSkipped",
                                    "reason": "invalid stop distance or qty",
                                }
                            )
                            continue

                        # Enforce MAX_POSITION_SIZE_USD
                        max_notional_usd = getattr(
                            hard_limits, "MAX_POSITION_SIZE_USD", 200000.0
                        )
                        if qty * current_close > max_notional_usd:
                            new_qty = max_notional_usd / current_close
                            _append_event(
                                {
                                    "event": "HardLimitPositionCapped",
                                    "original_qty": qty,
                                    "capped_qty": new_qty,
                                    "limit": max_notional_usd,
                                }
                            )
                            qty = new_qty

                        entry_price_slipped = apply_slippage(
                            current_close, True, False, slip_bps
                        )
                        entry_fees = calculate_fees(entry_price_slipped * qty, fees_bps)

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

                        _append_event(
                            {
                                "event": "PositionOpened",
                                "side": "SHORT",
                                "ts": candle.ts,
                                "price": entry_price_slipped,
                                "quantity": qty,
                                "stop": stop_price,
                                "tp": tp_price,
                            }
                        )

    # Update last_ts to the last processed candle
    state["last_ts"] = candles[-1].ts

    # Calculate unrealized PnL if position is open
    if state.get("position") is not None:
        position = state["position"]
        last_close = float(candles[-1].close)
        if position["side"] == "LONG":
            unrealized_pnl = (last_close - position["entry_price"]) * position[
                "quantity"
            ]
        else:
            unrealized_pnl = (position["entry_price"] - last_close) * position[
                "quantity"
            ]
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
    trades_csv_path = paper_dir / "trades.csv"
    if trades:
        fieldnames = [
            "trade_id",
            "side",
            "signal",
            "entry",
            "exit",
            "price",
            "quantity",
            "pnl",
            "fees",
            "entry_ts",
            "exit_ts",
            "timestamp",
            "exit_reason",
            "stop_price",
            "tp_price",
        ]
        temp_trades = trades_csv_path.with_suffix(".tmp")
        try:
            with temp_trades.open(
                "a" if trades_csv_path.exists() else "w", newline="", encoding="utf-8"
            ) as f:
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
