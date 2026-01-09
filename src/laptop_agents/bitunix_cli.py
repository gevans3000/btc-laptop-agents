from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import typer

import os
import time
from dotenv import load_dotenv

# Load env vars from .env if present
# ---------------- Paths (anchor to repo root) ----------------
HERE = Path(__file__).resolve()
REPO_ROOT = HERE.parent.parent.parent # bitunix_cli.py is in src/laptop_agents/
load_dotenv(REPO_ROOT / ".env")

from laptop_agents.data.providers.bitunix_futures import BitunixFuturesProvider

app = typer.Typer(add_completion=False, help="Bitunix tools for BTC Laptop Agents (public data + backtest runner).")

def resolve_cfg_path(path_str: str) -> Path:
    """Resolve config path relative to root if not found locally."""
    p = Path(path_str)
    if p.exists():
        return p
    
    # Try relative to repo root
    root_p = REPO_ROOT / path_str
    if root_p.exists():
        return root_p
        
    return p # return original (which might still not exist) to let caller handle error


@app.command()
def positions(
    symbol: str = typer.Option(None, help="Optional symbol filter (e.g. BTCUSDT)"),
):
    """Fetch current open positions (requires BITUNIX_API_KEY and BITUNIX_SECRET_KEY or BITUNIX_API_SECRET in env)."""
    api_key = os.getenv("BITUNIX_API_KEY")
    secret_key = os.getenv("BITUNIX_SECRET_KEY") or os.getenv("BITUNIX_API_SECRET")
    
    if not api_key:
        print("Error: BITUNIX_API_KEY is missing from environment or .env file.")
        raise typer.Exit(code=1)
    if not secret_key:
        print("Error: BITUNIX_SECRET_KEY (or BITUNIX_API_SECRET) is missing from environment or .env file.")
        raise typer.Exit(code=1)
        
    p = BitunixFuturesProvider(
        symbol=symbol or "BTCUSDT", # Default symbol required for init, even if fetching all positions
        api_key=api_key,
        secret_key=secret_key
    )
    
    try:
        data = p.get_pending_positions(symbol=symbol)
        if not data:
            print("No open positions found.")
        else:
            print(json.dumps(data, indent=2))
    except Exception as e:
        print(f"Error fetching positions: {e}")
        raise typer.Exit(code=1)


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
    from laptop_agents.agents.state import State
    from laptop_agents.indicators import Candle as CoreCandle

    p = BitunixFuturesProvider(symbol=symbol, allowed_symbols={symbol})

    # Load config the same way your main CLI does (keep it simple).
    path = resolve_cfg_path(cfg_path)
    if not path.exists():
        print(f"Error: Config file not found at {cfg_path} (resolved to {path})")
        raise typer.Exit(code=1)
        
    c = json.loads(path.read_text(encoding="utf-8"))
    c["instrument"] = c.get("instrument") or symbol
    c["timeframe"] = c.get("timeframe") or interval

    sup = Supervisor(provider=p, cfg=c, journal_path=journal_path)
    state = State(instrument=c["instrument"], timeframe=c["timeframe"])

    kl = p.klines_paged(interval=interval, total=limit)
    for i, k in enumerate(kl, start=1):
        # Convert provider candle to your core Candle
        candle = CoreCandle(ts=k.ts, open=k.open, high=k.high, low=k.low, close=k.close, volume=k.volume)
        sup.step(state, candle)
        if i % 50 == 0:
            snap = p.snapshot_derivatives()
            print(f"[{i}/{limit}] price={candle.close:,.0f} funding_8h={snap.get('funding_8h')} trade_id={state.trade_id}")

    print(f"Done. Journal: {journal_path}")


@app.command("live-session")
def live_session(
    symbol: str = typer.Option("BTCUSD", help="Bitunix futures symbol (ex: BTCUSD for BTC-M, BTCUSDT for USDT-M)."),
    interval: str = typer.Option("1m", help="Timeframe (e.g. 1m, 5m)."),
    duration_min: int = typer.Option(60, help="How many minutes to run this session."),
    cfg_path: str = typer.Option("config/default.json", help="Strategy configuration file."),
    shadow: bool = typer.Option(True, help="Shadow mode: simulate trades with live data but do not execute on exchange."),
):
    """Start a live trading session for a limited time (e.g., 1 hour).
    
    This command will fetch the latest market data every minute, run it through your
    agent pipeline, and execute trades on Bitunix if your criteria are met.
    """
    from laptop_agents.agents.supervisor import Supervisor
    from laptop_agents.agents.state import State
    from laptop_agents.indicators import Candle as CoreCandle

    api_key = os.getenv("BITUNIX_API_KEY")
    secret_key = os.getenv("BITUNIX_SECRET_KEY") or os.getenv("BITUNIX_API_SECRET")
    
    if not api_key or not secret_key:
        print("Error: BITUNIX_API_KEY and BITUNIX_SECRET_KEY must be set for live sessions.")
        raise typer.Exit(code=1)

    p = BitunixFuturesProvider(symbol=symbol, api_key=api_key, secret_key=secret_key)
    
    # Load config
    path = resolve_cfg_path(cfg_path)
    if not path.exists():
        print(f"Error: Config file not found at {cfg_path} (resolved to {path})")
        raise typer.Exit(code=1)
        
    c = json.loads(path.read_text(encoding="utf-8"))
    c["instrument"] = symbol
    c["timeframe"] = interval

    sup = Supervisor(provider=p, cfg=c)
    state = State(instrument=symbol, timeframe=interval)
    
    # Check for existing Bitunix positions to adopt
    print(f"[{'SHADOW' if shadow else 'LIVE'}] Checking for existing positions to adopt...")
    existing = p.get_pending_positions(symbol=symbol)
    if existing:
        pos = existing[0]
        print(f"Adopting existing {pos['side']} position: {pos['qty']} @ {pos.get('entryPrice')}")
        state.trade_id = pos.get("positionId", f"adopted_{int(time.time())}")

    # Pre-load history for indicators
    print(f"Pre-loading history for {symbol}...")
    kl = p.klines_paged(interval=interval, total=100)
    for k in kl:
        candle = CoreCandle(ts=k.ts, open=k.open, high=k.high, low=k.low, close=k.close, volume=k.volume)
        state.candles.append(candle)

    start_time = time.time()
    end_time = start_time + (duration_min * 60)
    
    mode_str = "SHADOW (Simulation)" if shadow else "LIVE (Real Trading)"
    print(f"Starting {duration_min} minute {mode_str} session for {symbol}...")
    
    while time.time() < end_time:
        try:
            # Fetch latest candle
            kl = p.klines(interval=interval, limit=1)
            if not kl:
                time.sleep(10)
                continue
                
            k = kl[0]
            candle = CoreCandle(ts=k.ts, open=k.open, high=k.high, low=k.low, close=k.close, volume=k.volume)
            
            # Pulse the supervisor
            state = sup.step(state, candle)
            
            # Check for entry event (shadowed from PaperBroker)
            ev = getattr(state, "broker_events", {})
            if ev.get("fill") and ev["fill"].get("side"):
                fill = ev["fill"]
                side = fill["side"]
                # For Bitunix BTCUSD, min contract is usually 1. 
                # For USDT-M, it varies but 0.001 BTC is common.
                # We will use the quantity from the agent but log it clearly.
                qty = float(fill["qty"])
                
                if shadow:
                    print(f"--- [SHADOW] WOULD EXECUTE: {side} {qty} @ {fill.get('price')} ---")
                    print(f"--- [SHADOW] TP: {fill.get('tp')} | SL: {fill.get('sl')} ---")
                else:
                    print(f"--- [LIVE] EXECUTING ORDER: {side} {qty} @ {fill.get('price')} ---")
                    try:
                        res = p.place_order(
                            side=side,
                            qty=qty,
                            tp_price=fill.get("tp"),
                            sl_price=fill.get("sl"),
                            symbol=symbol
                        )
                        print(f"Order Success: {json.dumps(res, indent=2)}")
                    except Exception as order_err:
                        print(f"Order Failed: {order_err}")
            
            # Check for exit event
            if ev.get("exit"):
                print(f"--- [EXIT SIGNAL] Reason: {ev['exit'].get('reason')} ---")
                # In live mode, TP/SL usually handles this on-exchange, 
                # but if agent forces exit, we should handle it here.
                if not shadow:
                    # Closing logic would go here if needed, 
                    # but current PaperBroker simulates hits.
                    pass
                
            elapsed_min = int((time.time() - start_time) / 60)
            remaining_min = duration_min - elapsed_min
            print(f"[{remaining_min}m left] Price: {candle.close:.2f} | TradeID: {state.trade_id}")
            
            # Sleep until next check (60s)
            time.sleep(60)
            
        except Exception as e:
            print(f"Session Error: {e}")
            time.sleep(30)

    print(f"Live session for {symbol} finished.")


def main():
    app()


if __name__ == "__main__":
    main()

