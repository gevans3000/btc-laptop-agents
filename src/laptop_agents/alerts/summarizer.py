"""LLM-assisted summarizer with offline-safe fallback.

If an LLM endpoint is configured (local or remote), it will produce a
concise explanation. Otherwise it generates a deterministic text summary
from the scored reasons.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from laptop_agents.alerts.scoring import AlertScore
from laptop_agents.alerts.budget import BudgetManager

logger = logging.getLogger("btc_alerts.summarizer")


def _build_prompt(score: AlertScore, price: float) -> str:
    """Build a concise LLM prompt from the alert score."""
    reasons_text = "\n".join(f"- {r}" for r in score.top_reasons)
    return (
        f"You are a concise Bitcoin market analyst. In 2-3 sentences, explain "
        f"why BTC (currently ${price:,.0f}) is showing a {score.regime} regime "
        f"with {score.confidence}% confidence.\n\n"
        f"Key factors:\n{reasons_text}\n\n"
        f"Be specific and actionable. No disclaimers."
    )


def _llm_summarize(
    prompt: str,
    endpoint: str,
    model: str,
    timeout: float = 15.0,
) -> Optional[str]:
    """Call an OpenAI-compatible chat completion endpoint."""
    try:
        resp = httpx.post(
            endpoint,
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150,
                "temperature": 0.3,
            },
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.warning("LLM summarize failed: %s", exc)
        return None


def _fallback_summary(score: AlertScore, price: float) -> str:
    """Deterministic fallback when LLM is unavailable."""
    regime_emoji = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}.get(
        score.regime, "⚪"
    )
    lines = [
        f"{regime_emoji} BTC ${price:,.0f} – {score.regime.upper()} ({score.confidence}% confidence)",
    ]
    if score.top_reasons:
        lines.append("Key drivers:")
        for i, r in enumerate(score.top_reasons[:3], 1):
            lines.append(f"  {i}. {r}")
    if score.trump_summary:
        lines.append(f"⚠️ Policy keywords: {score.trump_summary}")
    if score.data_quality != "ok":
        lines.append(f"📊 Data quality: {score.data_quality}")
    return "\n".join(lines)


def summarize(
    score: AlertScore,
    price: float,
    budget: Optional[BudgetManager] = None,
) -> str:
    """Produce a human-readable summary of the alert.

    Tries LLM if configured; falls back to deterministic text.
    """
    llm_endpoint = os.environ.get("ALERT_LLM_ENDPOINT", "")
    llm_model = os.environ.get("ALERT_LLM_MODEL", "local-model")

    if llm_endpoint:
        if budget and not budget.can_call("llm"):
            logger.info("LLM budget exhausted; using fallback summary")
        else:
            if budget:
                budget.record_call("llm")
            prompt = _build_prompt(score, price)
            result = _llm_summarize(prompt, llm_endpoint, llm_model)
            if result:
                return result
            logger.info("LLM returned empty; using fallback")

    return _fallback_summary(score, price)
