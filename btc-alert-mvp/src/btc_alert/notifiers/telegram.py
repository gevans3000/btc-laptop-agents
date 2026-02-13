import os

import httpx

from btc_alert.core.logger import logger


def send_telegram(message: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.info("Telegram not configured; skipping send.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    with httpx.Client(timeout=10) as client:
        resp = client.post(url, json={"chat_id": chat_id, "text": message})
        resp.raise_for_status()
    return True
