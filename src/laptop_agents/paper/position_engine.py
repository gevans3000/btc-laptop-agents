"""Position management and PnL calculation logic for PaperBroker."""

from __future__ import annotations
from typing import Any, Dict, Optional
from .broker_types import Position


def calculate_unrealized_pnl(
    pos: Optional[Position], current_price: float, is_inverse: bool
) -> float:
    """Calculate unrealized PnL for a position."""
    if pos is None or pos.qty <= 0:
        return 0.0

    if is_inverse:
        # Inverse PnL (USD) = Notional * (1/Entry - 1/Exit) * Exit for Long
        if pos.side == "LONG":
            pnl_coins = pos.qty * (1.0 / pos.entry - 1.0 / current_price)
        else:
            pnl_coins = pos.qty * (1.0 / current_price - 1.0 / pos.entry)
        return pnl_coins * current_price
    else:
        # Linear PnL (USDT) = (Exit - Entry) * Qty for Long
        if pos.side == "LONG":
            return (current_price - pos.entry) * pos.qty
        else:
            return (pos.entry - current_price) * pos.qty


def process_fifo_close(
    pos: Position,
    actual_qty: float,
    fill_px_slipped: float,
    exit_fee_rate: float,
    is_inverse: bool,
) -> Dict[str, Any]:
    """Execute FIFO closing logic for position reduction/exit."""
    remaining_qty = actual_qty
    total_realized_pnl = 0.0
    total_exit_fees = 0.0
    total_reduction = 0.0

    # side is the side of the EXECUTING order (e.g. SELL to close LONG)
    # the PnL calculation depends on the ORIGINAL position side
    pos_side = pos.side

    while remaining_qty > 0 and pos.lots:
        lot = pos.lots[0]
        signed_lot_qty = lot["qty"]

        # How much of this lot can we close?
        close_qty = min(remaining_qty, signed_lot_qty)

        # Settle this portion
        avg_entry = lot["price"]
        # Pro-rate entry fees for this lot portion
        entry_fees_portion = lot["fees"] * (close_qty / signed_lot_qty)

        if is_inverse:
            # pnl_coins = (1/Entry - 1/Exit) * Notional
            pnl_coins = (1.0 / avg_entry - 1.0 / fill_px_slipped) * close_qty
            if pos_side == "SHORT":
                pnl_coins = -pnl_coins
            pnl = pnl_coins * fill_px_slipped
        else:
            pnl = (
                (fill_px_slipped - avg_entry) * close_qty
                if pos_side == "LONG"
                else (avg_entry - fill_px_slipped) * close_qty
            )

        # Exit fees
        exit_fees = (
            abs(close_qty * fill_px_slipped if not is_inverse else close_qty)
            * exit_fee_rate
        )

        total_realized_pnl += pnl - exit_fees - entry_fees_portion
        total_exit_fees += exit_fees + entry_fees_portion
        total_reduction += close_qty

        if close_qty < lot["qty"]:
            lot["qty"] -= close_qty
            lot["fees"] -= entry_fees_portion
            remaining_qty = 0
        else:
            pos.lots.popleft()
            remaining_qty -= close_qty

    return {
        "realized_pnl": total_realized_pnl,
        "exit_fees": total_exit_fees,
        "reduction": total_reduction,
    }


def calculate_full_exit_pnl(
    pos: Position, px_slipped: float, exit_fee_rate: float, is_inverse: bool
) -> Dict[str, Any]:
    """Calculate PnL for exiting the entire position."""
    total_entry_notional = 0.0
    total_entry_fees = 0.0

    # Snapshot quantities before clearing lots
    qty = pos.qty

    # We use temporary list to avoid modifying pos.lots if it's purely a calculation
    # But in _exit we want to clear them.
    while pos.lots:
        lot = pos.lots.popleft()
        total_entry_notional += lot["qty"] * lot["price"]
        total_entry_fees += lot["fees"]

    avg_entry = total_entry_notional / qty if qty > 0 else px_slipped

    if is_inverse:
        if pos.side == "LONG":
            pnl_coins = qty * (1.0 / avg_entry - 1.0 / px_slipped)
        else:
            pnl_coins = qty * (1.0 / px_slipped - 1.0 / avg_entry)
        pnl = pnl_coins * px_slipped
        risk = qty * abs(1.0 / avg_entry - 1.0 / pos.sl) * px_slipped
    else:
        pnl = (
            (px_slipped - avg_entry) * qty
            if pos.side == "LONG"
            else (avg_entry - px_slipped) * qty
        )
        risk = abs(avg_entry - pos.sl) * qty

    exit_fees = abs(qty * px_slipped if not is_inverse else qty) * exit_fee_rate

    return {
        "avg_entry": avg_entry,
        "net_pnl": pnl - exit_fees - total_entry_fees,
        "total_fees": exit_fees + total_entry_fees,
        "risk": risk,
    }
