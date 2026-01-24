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

from laptop_agents import constants as hard_limits
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


def _load_or_init_state(
    paper_dir: Path,
    starting_balance: float,
    symbol: str,
    interval: str,
    source: str,
    fees_bps: float,
    slip_bps: float,
    risk_pct: float,
    stop_bps: float,
    tp_r: float,
    max_leverage: float,
    intrabar_mode: str,
) -> Dict[str, Any]:
    state_path = paper_dir / "state.json"
    if state_path.exists():
        with state_path.open("r", encoding="utf-8") as f:
            state = json.load(f)
        state.setdefault("risk_pct", risk_pct)
        state.setdefault("stop_bps", stop_bps)
        state.setdefault("tp_r", tp_r)
        state.setdefault("max_leverage", max_leverage)
        state.setdefault("intrabar_mode", intrabar_mode)
        state.setdefault("realized_pnl", 0.0)
        state.setdefault("unrealized_pnl", 0.0)
        state.setdefault("net_pnl", 0.0)
        state.setdefault("fees_total", 0.0)
        return state
    else:
        return {
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


def _open_paper_position(
    side: str,
    candle: Candle,
    state: Dict[str, Any],
    append_event: Callable,
) -> None:
    current_close = float(candle.close)
    qty, stop_price, tp_price = calculate_position_size(
        equity=state["equity"],
        entry_price=current_close,
        risk_pct=state["risk_pct"],
        stop_bps=state["stop_bps"],
        tp_r=state["tp_r"],
        max_leverage=state["max_leverage"],
        is_long=(side == "LONG"),
    )

    if qty is None:
        append_event(
            {"event": "RiskSizingSkipped", "reason": "invalid stop distance or qty"}
        )
        return

    max_notional_usd = getattr(hard_limits, "MAX_POSITION_SIZE_USD", 200000.0)
    if qty * current_close > max_notional_usd:
        new_qty = max_notional_usd / current_close
        append_event(
            {
                "event": "HardLimitPositionCapped",
                "original_qty": qty,
                "capped_qty": new_qty,
                "limit": max_notional_usd,
            }
        )
        qty = new_qty

    entry_price_slipped = apply_slippage(
        current_close, True, (side == "LONG"), state["slip_bps"]
    )
    entry_fees = calculate_fees(entry_price_slipped * qty, state["fees_bps"])

    state["position"] = {
        "side": side,
        "entry_price": entry_price_slipped,
        "entry_ts": candle.ts,
        "quantity": qty,
        "stop_price": stop_price,
        "tp_price": tp_price,
    }
    state["equity"] -= entry_fees
    state["fees_total"] = state.get("fees_total", 0.0) + entry_fees

    append_event(
        {
            "event": "PositionOpened",
            "side": side,
            "ts": candle.ts,
            "price": entry_price_slipped,
            "quantity": qty,
            "stop": stop_price,
            "tp": tp_price,
        }
    )


def _close_paper_position(
    exit_reason: str,
    exit_price: float,
    candle: Candle,
    state: Dict[str, Any],
    trades: List[Dict[str, Any]],
    append_event: Callable,
) -> None:
    position = state["position"]
    if not position:
        return

    exit_price_slipped = apply_slippage(
        exit_price, False, (position["side"] == "LONG"), state["slip_bps"]
    )

    if position["side"] == "LONG":
        pnl = (exit_price_slipped - position["entry_price"]) * position["quantity"]
    else:
        pnl = (position["entry_price"] - exit_price_slipped) * position["quantity"]

    exit_fees = calculate_fees(
        exit_price_slipped * position["quantity"], state["fees_bps"]
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
    state["realized_pnl"] = state.get("realized_pnl", 0.0) + (pnl - exit_fees)
    state["position"] = None

    append_event(
        {
            "event": "PositionClosed",
            "side": position["side"],
            "ts": candle.ts,
            "price": exit_price_slipped,
            "pnl": pnl - exit_fees,
            "reason": exit_reason,
        }
    )


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
    if paper_dir is None:
        paper_dir = Path("paper")
    paper_dir.mkdir(exist_ok=True)

    def append_event(obj: Dict[str, Any]):
        if append_event_fn:
            append_event_fn(obj, paper=True)
        else:
            obj.setdefault("timestamp", utc_ts())
            with (paper_dir / "events.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    # Enforce hard limits
    actual_max_leverage = min(max_leverage, getattr(hard_limits, "MAX_LEVERAGE", 20.0))
    if actual_max_leverage != max_leverage:
        append_event(
            {
                "event": "HardLimitLeverageCapped",
                "requested": max_leverage,
                "capped": actual_max_leverage,
            }
        )
        max_leverage = actual_max_leverage

    actual_tp_r = max(tp_r, getattr(hard_limits, "MIN_RR_RATIO", 1.0))
    if actual_tp_r != tp_r:
        append_event(
            {"event": "HardLimitRRCapped", "requested": tp_r, "capped": actual_tp_r}
        )
        tp_r = actual_tp_r

    state = _load_or_init_state(
        paper_dir,
        starting_balance,
        symbol,
        interval,
        source,
        fees_bps,
        slip_bps,
        risk_pct,
        stop_bps,
        tp_r,
        max_leverage,
        intrabar_mode,
    )

    max_daily_loss = getattr(hard_limits, "MAX_DAILY_LOSS_USD", 50.0)
    if state.get("realized_pnl", 0.0) <= -max_daily_loss:
        append_event(
            {
                "event": "HardLimitDailyLossReached",
                "pnl": state["realized_pnl"],
                "limit": max_daily_loss,
            }
        )
        return [], state["equity"], state

    last_ts = state.get("last_ts")
    new_candles = [c for c in candles if last_ts is None or c.ts > last_ts]
    if not new_candles:
        return [], state["equity"], state

    trades: List[Dict[str, Any]] = []
    from laptop_agents.trading.strategy import SMACrossoverStrategy

    strategy = SMACrossoverStrategy()

    for candle in new_candles:
        candles_subset = [c for c in candles if c.ts <= candle.ts]
        signal = strategy.generate_signal(candles_subset)
        if signal is None:
            state["last_ts"] = candle.ts
            continue

        pos = state.get("position")
        if not pos:
            if signal in ["BUY", "SELL"]:
                _open_paper_position(
                    "LONG" if signal == "BUY" else "SHORT", candle, state, append_event
                )
        else:
            # Check exit conditions
            exit_reason: str | None = None
            exit_price: float = 0.0
            cur_h, cur_l, cur_c = (
                float(candle.high),
                float(candle.low),
                float(candle.close),
            )

            if pos["side"] == "LONG":
                stop_hit, tp_hit = cur_l <= pos["stop_price"], cur_h >= pos["tp_price"]
                if stop_hit and tp_hit:
                    exit_reason, exit_price = (
                        ("STOP", pos["stop_price"])
                        if intrabar_mode == "conservative"
                        else ("TP", pos["tp_price"])
                    )
                elif stop_hit:
                    exit_reason, exit_price = "STOP", pos["stop_price"]
                elif tp_hit:
                    exit_reason, exit_price = "TP", pos["tp_price"]
                elif signal == "SELL":
                    exit_reason, exit_price = "REVERSE", cur_c
            else:
                stop_hit, tp_hit = cur_h >= pos["stop_price"], cur_l <= pos["tp_price"]
                if stop_hit and tp_hit:
                    exit_reason, exit_price = (
                        ("STOP", pos["stop_price"])
                        if intrabar_mode == "conservative"
                        else ("TP", pos["tp_price"])
                    )
                elif stop_hit:
                    exit_reason, exit_price = "STOP", pos["stop_price"]
                elif tp_hit:
                    exit_reason, exit_price = "TP", pos["tp_price"]
                elif signal == "BUY":
                    exit_reason, exit_price = "REVERSE", cur_c

            if exit_reason:
                _close_paper_position(
                    exit_reason, exit_price, candle, state, trades, append_event
                )
                # Handle reversal
                if (
                    exit_reason == "REVERSE"
                    and state.get("realized_pnl", 0.0) > -max_daily_loss
                ):
                    _open_paper_position(
                        "LONG" if signal == "BUY" else "SHORT",
                        candle,
                        state,
                        append_event,
                    )

        state["last_ts"] = candle.ts

    # Final updates
    if state.get("position"):
        p = state["position"]
        lc = float(candles[-1].close)
        state["unrealized_pnl"] = (
            (lc - p["entry_price"]) * p["quantity"]
            if p["side"] == "LONG"
            else (p["entry_price"] - lc) * p["quantity"]
        )
    else:
        state["unrealized_pnl"] = 0.0
    state["net_pnl"] = state.get("realized_pnl", 0.0) + state.get("unrealized_pnl", 0.0)

    # Persistence
    from laptop_agents.core.state_manager import StateManager

    StateManager.atomic_save_json(paper_dir / "state.json", state)

    if trades:
        _save_trades_to_csv(paper_dir / "trades.csv", trades)

    return trades, state["equity"], state


def _save_trades_to_csv(path: Path, trades: List[Dict[str, Any]]) -> None:
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
    try:
        with path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if path.stat().st_size == 0:
                writer.writeheader()
            for t in trades:
                writer.writerow({k: v for k, v in t.items() if k in fieldnames})
            f.flush()
            import os

            os.fsync(f.fileno())
    except Exception as e:
        raise RuntimeError(f"Failed to append to trades.csv: {e}")
