"""Alert message formatter – builds the final Telegram message."""

from __future__ import annotations

from datetime import datetime, timezone


from laptop_agents.alerts.scoring import AlertScore


def format_alert_message(
    score: AlertScore,
    price: float,
    summary: str,
    next_check_minutes: int = 15,
    momentum_pct: float = 0.0,
) -> str:
    """Format a structured Telegram alert message.

    Returns Markdown-formatted text matching the alert spec:
    price, regime, confidence, top reasons, trump keywords,
    data quality, and next check time.
    """
    regime_emoji = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}.get(
        score.regime, "⚪"
    )
    direction = "📈" if momentum_pct > 0 else "📉" if momentum_pct < 0 else "➡️"

    lines = [
        f"*{regime_emoji} BTC Alert – {score.regime.upper()}*",
        "",
        f"💰 *Price:* ${price:,.2f} {direction} ({momentum_pct:+.2f}%)",
        f"📊 *Regime:* {score.regime.capitalize()}",
        f"🎯 *Confidence:* {score.confidence}/100",
        "",
    ]

    # Top reasons
    if score.top_reasons:
        lines.append("*Top Reasons:*")
        for i, reason in enumerate(score.top_reasons[:5], 1):
            lines.append(f"  {i}. {reason}")
        lines.append("")

    # Trump/policy
    if score.trump_summary:
        lines.append(f"🏛️ *Policy Keywords:* {score.trump_summary}")
        lines.append("")

    # LLM summary
    if summary:
        lines.append(f"💡 *Analysis:* {summary}")
        lines.append("")

    # Data quality
    if score.data_quality != "ok":
        degraded_str = ", ".join(score.degraded_sources) if score.degraded_sources else "some"
        lines.append(f"⚠️ *Data Quality:* {score.data_quality} (degraded: {degraded_str})")
        lines.append("")

    # Next check
    now = datetime.now(timezone.utc)
    next_time = now.timestamp() + next_check_minutes * 60
    next_dt = datetime.fromtimestamp(next_time, tz=timezone.utc)
    lines.append(f"⏰ *Next check:* {next_dt.strftime('%H:%M UTC')}")

    return "\n".join(lines)
