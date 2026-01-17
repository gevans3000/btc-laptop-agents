"""Optional Telegram alerts for trade notifications."""

import os
import httpx
from typing import Optional

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def send_alert(message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        httpx.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message})
        return True
    except Exception:
        return False


def alert_trade(side: str, entry: float, qty: float, pnl: Optional[float] = None):
    msg = f"🔔 Trade: {side}\nEntry: ${entry:,.2f}\nQty: {qty}"
    if pnl is not None:
        msg += f"\nPnL: ${pnl:.2f}"
    send_alert(msg)
