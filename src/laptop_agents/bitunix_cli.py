from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import typer

from laptop_agents.data.providers.bitunix_futures import BitunixFuturesProvider

app = typer.Typer(add_completion=False, help="Bitunix tools for BTC Laptop Agents (public data + backtest runner).")


@app.command()
def probe(
    symbol: str = typer.Option("BTCUSD", help="Bitunix futures symbol to probe (ex: BTCUSD or BTCUSDT)."),
    interval: str = typer.Option("5m", help="Kline interval (ex: 5m)."),
    limit: int = typer.Option(50, help="How many candles to fetch (max 200 per request)."),
):
    """Quick connectivity check: trading_pairs + tickers + funding + last candle."""
    p = BitunixFuturesProvider(symbol=symbol, allowed_symbols={symbol})
    pairs = p.trading_pairs()
    ticks = p.tickers()
    fund = p.funding_rate()
    kl = p.klines_paged(interval=interval, total=min(limit, 200))

    last_close = kl[-1].close if kl else None
    out = {
        "symbol": symbol,
        "interval": interval,
        "last_close": last_close,
        "funding_8h": fund,
        "trading_pairs_count": len(pairs),
        "tickers_count": len(ticks),
    }
    print(json.dumps(out, indent=2))


@app.command("run-history")
def run_history(
    symbol: str = typer.Option("BTCUSD", help="Bitunix futures symbol (ex: BTCUSD)."),
    interval: str = typer.Option("5m", help="Kline interval (ex: 5m)."),
    limit: int = typer.Option(300, help="How many candles to simulate through."),
    cfg_path: str = typer.Option("config/default.json", help="Your existing stack config (setups/risk gates)."),
    journal_path: str = typer.Option("data/paper_journal.jsonl", help="Paper journal path."),
):
    """Run your existing 5-agent pipeline over Bitunix historical candles (acts like a backtest slice)."""
    # Import your existing supervisor/state/candle wiring (already in your repo).
    from laptop_agents.agents.supervisor import Supervisor
    from laptop_agents.core.state import State, Candle as CoreCandle  # type: ignore

    p = BitunixFuturesProvider(symbol=symbol, allowed_symbols={symbol})

    # Load config the same way your main CLI does (keep it simple).
    c = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
    c["instrument"] = c.get("instrument") or symbol
    c["timeframe"] = c.get("timeframe") or interval

    sup = Supervisor(provider=p, cfg=c, journal_path=journal_path)
    state = State(instrument=c["instrument"], timeframe=c["timeframe"])

    kl = p.klines_paged(interval=interval, total=limit)
    for i, k in enumerate(kl, start=1):
        # Convert provider candle to your core Candle
        candle = CoreCandle(ts=k.ts, open=k.open, high=k.high, low=k.low, close=k.close, vol=k.vol)
        sup.on_candle(state, candle)
        if i % 50 == 0:
            snap = p.snapshot_derivatives()
            print(f"[{i}/{limit}] price={candle.close:,.0f} funding_8h={snap.get('funding_8h')} trade_id={state.trade_id}")

    print(f"Done. Journal: {journal_path}")


def main():
    app()


if __name__ == "__main__":
    main()

