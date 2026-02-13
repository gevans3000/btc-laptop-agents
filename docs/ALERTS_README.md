# BTC Alert System

A free-tier, laptop-local Bitcoin alert system with Telegram notifications.

## What It Does

Monitors BTC price and market conditions every 15 minutes, then sends a scored, explained Telegram alert containing:

- **Price + short-horizon move** (momentum %)
- **Regime**: bullish / bearish / neutral
- **Confidence**: 0–100 deterministic score
- **Top 3–5 reasons** ranked by impact
- **Trump/policy/macro keyword hits** (if any in recent news)
- **Data quality note** (degraded mode if sources fail)
- **Next check time**

## Data Sources (all free, no API keys)

| Source | What | Rate Limit |
|--------|------|------------|
| Binance `/api/v3` | Price & candles | 10 calls/min |
| Alternative.me F&G | Fear & Greed Index | 5 calls/5min |
| CoinTelegraph RSS | News headlines | 20 feeds/5min |
| CoinDesk RSS | News headlines | (shared budget) |

All sources degrade gracefully — if one fails, the system continues with remaining data.

## Quick Start

### 1. Prerequisites
- Python 3.12+
- The repo's virtualenv (`.venv`)

### 2. Configure Telegram (optional but recommended)

Create/edit your `.env` file at the repo root:

```bash
# Copy from .env.alerts.example
TELEGRAM_BOT_TOKEN="your-bot-token"
TELEGRAM_CHAT_ID="your-chat-id"
```

**To get a Telegram bot token:**
1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow prompts
3. Copy the token

**To get your chat ID:**
1. Message your bot
2. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Find `"chat":{"id":123456789}` in the response

If Telegram is not configured, alerts print to the console instead.

### 3. Run

```bash
# Single alert cycle (test it works)
la alert --once

# Continuous loop (default: every 15 minutes)
la alert

# With debug logging
la alert --verbose

# Custom config
la alert --config path/to/alerts.yaml
```

### 4. Optional: LLM-Assisted Summaries

Add to your `.env`:

```bash
# Local LM Studio
ALERT_LLM_ENDPOINT="http://localhost:1234/v1/chat/completions"
ALERT_LLM_MODEL="local-model"
```

If the LLM is unavailable, a deterministic text summary is used instead.

## Configuration

Edit `config/alerts.yaml`:

```yaml
alerts:
  interval_minutes: 15      # check frequency
  cooldown_seconds: 300      # min time between Telegram messages
  candle_interval: "1h"      # candle timeframe
  candle_limit: 50           # number of candles to fetch
  confidence_threshold: 0    # 0 = always alert; 10 = only alert on stronger signals
```

## Architecture

```
src/laptop_agents/alerts/
├── __init__.py
├── budget.py              # Per-source rate-limit manager
├── cli.py                 # CLI entry point
├── formatter.py           # Telegram message builder
├── pipeline.py            # Orchestration loop
├── scoring.py             # Deterministic scoring engine
├── summarizer.py          # LLM hook + offline fallback
├── collectors/
│   ├── __init__.py
│   ├── price.py           # Binance price & candles
│   ├── fear_greed.py      # Alternative.me Fear & Greed
│   └── news.py            # RSS headline fetcher
└── features/
    ├── __init__.py
    ├── technicals.py      # EMA, volatility, momentum
    └── keywords.py        # Trump/policy/macro keyword scanner
```

## Scoring Logic

The engine assigns a **deterministic confidence score** (0–100) from a neutral baseline of 50:

| Signal | Range | Effect |
|--------|-------|--------|
| EMA cross (bullish/bearish) | ±15 | Trend direction |
| Momentum % | ±15 | Recent price action |
| Volatility | –10 | High vol = uncertainty |
| Fear & Greed extremes | ±10 | Contrarian signal |
| News keyword sentiment | ±15 | Headline-driven bias |

**Regime**: bullish (>55), bearish (<45), neutral (45–55)

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Telegram not configured` | Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env` |
| All sources degraded | Check internet connection; system still runs with cached/fallback data |
| No alerts sent | Check cooldown period (default 5min); try `--once` for immediate test |
| Import errors | Run `pip install -e .` from repo root |

## Tests

```bash
# Run alert-specific tests
pytest tests/test_alerts_*.py -v

# Run all repo tests
pytest tests/ -v
```
