"""Telegram alert notifier with dedup and cooldown."""

from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

import httpx

logger = logging.getLogger("btc_alerts.telegram")

TELEGRAM_API = "https://api.telegram.org"


@dataclass
class TelegramNotifier:
    """Send alert messages to a Telegram chat with dedup/cooldown.

    Configuration via environment variables:
    - ``TELEGRAM_BOT_TOKEN``: Bot API token
    - ``TELEGRAM_CHAT_ID``: Target chat/channel ID
    """

    bot_token: str = ""
    chat_id: str = ""
    cooldown_seconds: float = 300.0  # minimum seconds between alerts
    _sent_hashes: Dict[str, float] = field(default_factory=dict)
    _last_send_time: float = 0.0

    def __post_init__(self) -> None:
        if not self.bot_token:
            self.bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not self.chat_id:
            self.chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    @property
    def configured(self) -> bool:
        """Return True if bot token and chat ID are set."""
        return bool(self.bot_token and self.chat_id)

    def _message_hash(self, text: str) -> str:
        """Hash first 200 chars to detect near-duplicate alerts."""
        return hashlib.md5(text[:200].encode()).hexdigest()

    def _is_duplicate(self, text: str) -> bool:
        """Check if a similar message was sent recently."""
        h = self._message_hash(text)
        now = time.time()
        # Prune old entries
        self._sent_hashes = {
            k: v for k, v in self._sent_hashes.items()
            if now - v < self.cooldown_seconds * 3
        }
        if h in self._sent_hashes:
            elapsed = now - self._sent_hashes[h]
            if elapsed < self.cooldown_seconds:
                return True
        return False

    def _in_cooldown(self) -> bool:
        """Check if we're still in global cooldown."""
        return (time.time() - self._last_send_time) < self.cooldown_seconds

    def send(
        self,
        text: str,
        force: bool = False,
        timeout: float = 10.0,
    ) -> bool:
        """Send a message to the configured Telegram chat.

        Args:
            text: Message text (supports Markdown).
            force: Skip dedup/cooldown checks.
            timeout: HTTP request timeout.

        Returns:
            True if message was sent or skipped (dedup), False on error.
        """
        if not self.configured:
            logger.warning("Telegram not configured; printing alert to console")
            print(f"\n{'='*60}\n📢 ALERT (Telegram not configured)\n{'='*60}\n{text}\n{'='*60}\n")
            return False

        if not force:
            if self._in_cooldown():
                logger.info("Telegram cooldown active; skipping send")
                return True
            if self._is_duplicate(text):
                logger.info("Duplicate alert detected; skipping send")
                return True

        url = f"{TELEGRAM_API}/bot{self.bot_token}/sendMessage"
        try:
            resp = httpx.post(
                url,
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            self._sent_hashes[self._message_hash(text)] = time.time()
            self._last_send_time = time.time()
            logger.info("Telegram alert sent successfully")
            return True
        except Exception as exc:
            logger.error("Telegram send failed: %s", exc)
            return False
