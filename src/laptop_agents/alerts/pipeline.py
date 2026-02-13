"""Alert pipeline – orchestrates collect → score → summarize → notify loop."""

from __future__ import annotations

import logging
import os
import time

import yaml

from laptop_agents.alerts.budget import BudgetManager
from laptop_agents.alerts.collectors.price import fetch_btc_price, fetch_btc_candles
from laptop_agents.alerts.collectors.fear_greed import fetch_fear_greed
from laptop_agents.alerts.collectors.news import fetch_news_headlines
from laptop_agents.alerts.features.technicals import compute_technical_features
from laptop_agents.alerts.features.keywords import scan_keywords
from laptop_agents.alerts.scoring import compute_score
from laptop_agents.alerts.summarizer import summarize
from laptop_agents.alerts.formatter import format_alert_message
from laptop_agents.alerts.telegram_notifier import TelegramNotifier

logger = logging.getLogger("btc_alerts.pipeline")


def _load_config(config_path: str | None = None) -> dict:
    """Load alerts.yaml config with sane defaults."""
    defaults = {
        "interval_minutes": 15,
        "cooldown_seconds": 300,
        "candle_interval": "1h",
        "candle_limit": 50,
        "confidence_threshold": 0,  # 0 = always alert
    }
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path) as f:
                user_cfg = yaml.safe_load(f) or {}
            defaults.update(user_cfg.get("alerts", user_cfg))
        except Exception as exc:
            logger.warning("Failed to load config %s: %s", config_path, exc)
    return defaults


def run_once(
    budget: BudgetManager,
    notifier: TelegramNotifier,
    config: dict,
) -> bool:
    """Execute one full alert cycle.

    Returns True if an alert was generated/sent, False otherwise.
    """
    logger.info("--- Alert cycle start ---")

    # 1. Collect data
    price_snap = fetch_btc_price(budget=budget)
    candles = fetch_btc_candles(
        interval=config.get("candle_interval", "1h"),
        limit=config.get("candle_limit", 50),
        budget=budget,
    )
    fg = fetch_fear_greed(budget=budget)
    news = fetch_news_headlines(budget=budget)

    # 2. Extract features
    technicals = compute_technical_features(candles)
    kw_result = scan_keywords(news.headlines)

    # Use candle price if ticker failed
    price = price_snap.price
    if price <= 0 and technicals.price > 0:
        price = technicals.price

    # 3. Score
    score = compute_score(technicals, kw_result, fg)

    # Skip if below confidence threshold
    threshold = config.get("confidence_threshold", 0)
    if abs(score.confidence - 50) < threshold:
        logger.info(
            "Confidence %d within threshold %d of neutral; skipping alert",
            score.confidence, threshold,
        )
        return False

    # 4. Summarize
    summary = summarize(score, price, budget=budget)

    # 5. Format
    interval = config.get("interval_minutes", 15)
    message = format_alert_message(
        score=score,
        price=price,
        summary=summary,
        next_check_minutes=interval,
        momentum_pct=technicals.momentum_pct,
    )

    # 6. Notify
    sent = notifier.send(message)

    logger.info(
        "Alert cycle done: regime=%s confidence=%d sent=%s",
        score.regime, score.confidence, sent,
    )
    return sent


def run_loop(
    config_path: str | None = None,
    max_iterations: int = 0,
) -> None:
    """Run the alert pipeline in a loop.

    Args:
        config_path: Path to alerts.yaml.
        max_iterations: If >0, stop after this many cycles (for testing).
    """
    config = _load_config(config_path)
    budget = BudgetManager()
    notifier = TelegramNotifier(
        cooldown_seconds=config.get("cooldown_seconds", 300.0),
    )

    interval = config.get("interval_minutes", 15) * 60
    iteration = 0

    logger.info(
        "Alert loop starting – interval=%dmin threshold=%d telegram=%s",
        config.get("interval_minutes", 15),
        config.get("confidence_threshold", 0),
        "configured" if notifier.configured else "NOT configured (console only)",
    )

    while True:
        try:
            run_once(budget, notifier, config)
        except Exception as exc:
            logger.error("Alert cycle failed: %s", exc, exc_info=True)

        iteration += 1
        if 0 < max_iterations <= iteration:
            logger.info("Reached max iterations (%d); exiting", max_iterations)
            break

        logger.info("Sleeping %d seconds until next cycle", interval)
        time.sleep(interval)
