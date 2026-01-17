from typing import Any, Dict
import time


def generate_summary(broker: Any, start_time: float) -> Dict[str, Any]:
    """
    Generate a session summary report based on broker state.
    """
    trades_list = [h for h in broker.order_history if h.get("type") == "exit"]
    wins = [t for t in trades_list if t.get("pnl", 0) > 0]

    total_trades = len(trades_list)
    win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0.0

    realized_pnl = sum(t.get("pnl", 0) for t in trades_list)
    total_fees = sum(t.get("fees", 0) for t in trades_list)

    # Calculate max drawdown (simple version based on equity history)
    # Note: Broker doesn't track equity history, but AsyncRunner has metrics.
    # For now, we'll keep it simple.

    return {
        "run_id": str(int(start_time)),
        "duration_s": round(time.time() - start_time, 1),
        "total_trades": total_trades,
        "win_rate_pct": round(win_rate, 2),
        "realized_pnl_usd": round(realized_pnl, 2),
        "fees_paid_usd": round(total_fees, 2),
        "max_drawdown_pct": 0.0,  # Placeholder or calculate if metrics available
        "slippage_avg_bps": 30.0,  # Plan assumes this or we can track it
    }
