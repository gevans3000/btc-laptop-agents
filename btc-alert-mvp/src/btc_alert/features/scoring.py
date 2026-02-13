def score_trigger(market: dict, momentum: dict, volatility: dict, sentiment: dict, fear_greed: dict) -> dict:
    score = 0.0
    score += momentum.get("ema_momentum", 0.0) * 100
    score += max(min(market.get("price_change_percent", 0.0), 8), -8) * 0.5
    score += (sentiment.get("sentiment_score", 0.0) * 2)

    fg = fear_greed.get("value", 50)
    if fg >= 75:
        score -= 0.8
    elif fg <= 25:
        score += 0.8

    vol = volatility.get("volatility", 0.0)
    if vol > 0.03:
        score += 0.5

    label = "watch"
    if score >= 1.5:
        label = "bullish_alert"
    elif score <= -1.5:
        label = "bearish_alert"

    return {"trigger_score": round(score, 4), "trigger_label": label}
