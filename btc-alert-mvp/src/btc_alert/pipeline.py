import time

from btc_alert.collectors.fear_greed import fetch_fear_greed
from btc_alert.collectors.market import fetch_market_snapshot
from btc_alert.collectors.news import collect_news_snapshot
from btc_alert.collectors.price import fetch_klines
from btc_alert.collectors.sentiment import collect_sentiment_snapshot
from btc_alert.core.logger import logger
from btc_alert.features.momentum import compute_momentum
from btc_alert.features.scoring import score_trigger
from btc_alert.features.volatility import compute_volatility
from btc_alert.notifiers.telegram import send_telegram
from btc_alert.store.state_store import AlertStateStore
from btc_alert.summarizer.llm import synthesize_alert_text


def run_pipeline(symbol: str, interval: int, cooldown: int = 900) -> None:
    store = AlertStateStore()
    while True:
        try:
            closes = fetch_klines(symbol=symbol)
            market = fetch_market_snapshot(symbol=symbol)
            sentiment = collect_sentiment_snapshot(symbol=symbol)
            _news = collect_news_snapshot(symbol=symbol)
            fear_greed = fetch_fear_greed()

            momentum = compute_momentum(closes)
            volatility = compute_volatility(closes)
            trigger = score_trigger(market, momentum, volatility, sentiment, fear_greed)

            payload = {
                "symbol": symbol,
                "trigger_score": trigger["trigger_score"],
                "trigger_label": trigger["trigger_label"],
                "momentum_regime": momentum["momentum_regime"],
                "price_change_percent": market["price_change_percent"],
                "fear_greed_value": fear_greed["value"],
            }
            message = synthesize_alert_text(payload)

            if store.should_send(message, cooldown_s=cooldown):
                sent = send_telegram(message)
                logger.info("alert_emitted sent=%s message=%s", sent, message)
                store.mark_sent(message)
            else:
                logger.info("alert_suppressed cooldown=%ss", cooldown)

        except Exception as exc:  # noqa: BLE001
            logger.exception("pipeline_error: %s", exc)

        time.sleep(interval)
