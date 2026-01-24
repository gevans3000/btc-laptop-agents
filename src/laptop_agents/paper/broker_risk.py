"""Risk validation logic for PaperBroker."""
from __future__ import annotations
import math
import time
from typing import Any, Dict, List, Protocol

from laptop_agents import constants as hard_limits
from laptop_agents.core.events import append_event
from laptop_agents.core.logger import logger

class BrokerRiskInterface(Protocol):
    symbol: str
    order_timestamps: List[float]
    last_trade_time: float
    min_trade_interval_sec: float
    starting_equity: float
    max_position_per_symbol: Dict[str, float]

def validate_risk_limits(
    broker: BrokerRiskInterface,
    order: Dict[str, Any],
    candle: Any,
    equity: float,
    is_working: bool,
) -> bool:
    """Validate all risk limits, throttling, and hard constraints."""
    # Trade frequency throttle
    now = time.time()

    # Rate limiting (orders per minute)
    broker.order_timestamps = [t for t in broker.order_timestamps if now - t < 60]
    if len(broker.order_timestamps) >= hard_limits.MAX_ORDERS_PER_MINUTE:
        logger.warning(
            f"REJECTED: Rate limit {hard_limits.MAX_ORDERS_PER_MINUTE} orders/min exceeded"
        )
        append_event(
            {"event": "OrderRejected", "reason": "rate_limit_exceeded"}, paper=True
        )
        return False
    broker.order_timestamps.append(now)

    # Trade frequency throttle (min_trade_interval_sec)
    time_since_last = now - broker.last_trade_time
    if not is_working and time_since_last < broker.min_trade_interval_sec:
        logger.warning(
            f"REJECTED: Trade throttling. {time_since_last:.1f}s < {broker.min_trade_interval_sec}s"
        )
        append_event(
            {
                "event": "OrderThrottled",
                "interval_sec": broker.min_trade_interval_sec,
            },
            paper=True,
        )
        return False

    # Daily loss check
    max_daily_loss_usd = getattr(hard_limits, "MAX_DAILY_LOSS_USD", 50.0)
    drawdown_usd = broker.starting_equity - equity
    if broker.starting_equity and drawdown_usd >= max_daily_loss_usd:
        logger.warning(
            f"REJECTED: Daily loss ${drawdown_usd:.2f} >= ${max_daily_loss_usd}"
        )
        append_event(
            {
                "event": "OrderRejected",
                "reason": "daily_loss_usd_exceeded",
                "drawdown_usd": drawdown_usd,
                "limit_usd": max_daily_loss_usd,
            },
            paper=True,
        )
        return False
    drawdown_pct = (broker.starting_equity - equity) / broker.starting_equity * 100.0
    if drawdown_pct > hard_limits.MAX_DAILY_LOSS_PCT:
        logger.warning(
            f"REJECTED: Daily loss {drawdown_pct:.2f}% > {hard_limits.MAX_DAILY_LOSS_PCT}%"
        )
        append_event(
            {
                "event": "OrderRejected",
                "reason": "daily_loss_exceeded",
                "drawdown_pct": drawdown_pct,
            },
            paper=True,
        )
        return False

    # Position Cap Check
    qty_requested = float(order.get("qty", 0))
    symbol_cap = broker.max_position_per_symbol.get(
        broker.symbol, hard_limits.MAX_POSITION_ABS
    )
    if qty_requested > symbol_cap:
        logger.warning(
            f"REJECTED: Position limit exceeded for {broker.symbol}. Requested {qty_requested} > Cap {symbol_cap}"
        )
        append_event(
            {
                "event": "OrderRejected",
                "reason": "position_limit_exceeded",
                "symbol": broker.symbol,
                "requested": qty_requested,
                "cap": symbol_cap,
            },
            paper=True,
        )
        return False

    # HARD LIMIT ENFORCEMENT
    entry_px_est = float(candle.close)
    if entry_px_est <= 0:
        logger.error("REJECTED: Entry price estimate is zero or negative")
        return False
    qty_est = float(order["qty"])
    notional_est = qty_est * entry_px_est

    if notional_est > hard_limits.MAX_POSITION_SIZE_USD:
        logger.warning(
            f"PAPER REJECTED: Notional ${notional_est:.2f} > hard limit ${hard_limits.MAX_POSITION_SIZE_USD}"
        )
        append_event(
            {
                "event": "OrderRejected",
                "reason": "notional_exceeded",
                "notional": notional_est,
            },
            paper=True,
        )
        return False

    leverage_est = notional_est / equity
    if leverage_est > hard_limits.MAX_LEVERAGE:
        logger.warning(
            f"PAPER REJECTED: Leverage {leverage_est:.1f}x > hard limit {hard_limits.MAX_LEVERAGE}x"
        )
        append_event(
            {
                "event": "OrderRejected",
                "reason": "leverage_exceeded",
                "leverage": leverage_est,
            },
            paper=True,
        )
        return False

    entry = float(order["entry"])
    side = order["side"]
    qty = float(order["qty"])
    sl = float(order["sl"])
    tp = float(order["tp"])

    if side not in {"LONG", "SHORT"}:
        logger.warning("REJECTED: Invalid side")
        return False
    if sl <= 0 or tp <= 0:
        logger.warning("REJECTED: Non-positive SL/TP")
        return False
    if not all(math.isfinite(x) for x in [entry, qty, sl, tp]):
        logger.warning("REJECTED: Non-finite order fields")
        return False
    if qty <= 0 or entry <= 0:
        logger.warning("REJECTED: Non-positive entry/qty")
        return False

    # Single Trade Loss Cap
    risk_dollars = abs(entry - sl) * qty
    if risk_dollars > hard_limits.MAX_SINGLE_TRADE_LOSS_USD:
        logger.warning(
            f"REJECTED: Risk ${risk_dollars:.2f} > Max ${hard_limits.MAX_SINGLE_TRADE_LOSS_USD}"
        )
        append_event(
            {
                "event": "OrderRejected",
                "reason": "risk_cap_exceeded",
                "risk": risk_dollars,
            },
            paper=True,
        )
        return False

    return True
