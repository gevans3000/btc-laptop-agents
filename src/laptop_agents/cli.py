from __future__ import annotations

import json
from pathlib import Path
import typer
from rich import print

from .agents import State, Supervisor
from .data.providers import (
    MockProvider,
    BinanceFuturesProvider,
    KrakenSpotProvider,
    BybitDerivativesProvider,
    OkxSwapProvider,
    CompositeProvider,
    BitunixFuturesProvider,
)
from .indicators import Candle

app = typer.Typer(help="BTC Laptop Agents — 5-agent paper trading loop (5m)")


# Robust path resolution
HERE = Path(__file__).resolve()
REPO_ROOT = HERE.parent.parent.parent

def load_cfg(path: str = "config/default.json") -> dict:
    """Load config with robust path resolution (CWD or REPO_ROOT)."""
    p = Path(path)
    if p.is_absolute():
        return json.loads(p.read_text(encoding="utf-8"))
    
    # Try CWD first
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
        
    # Try REPO_ROOT
    repo_p = REPO_ROOT / path
    if repo_p.exists():
        return json.loads(repo_p.read_text(encoding="utf-8"))
        
    raise FileNotFoundError(f"Config not found: {path} or {repo_p}")


@app.command()
def debug_feeds(cfg: str = "config/default.json"):
    c = load_cfg(cfg)
    sym = c["instrument"]
    tf = c["timeframe"]

    print("[bold]Bitunix Futures candles + derivatives[/bold]")
    try:
        b = BitunixFuturesProvider(symbol=sym, allowed_symbols={sym})
        kl = b.klines(interval=tf, limit=5)
        d = b.snapshot_derivatives()
        print(f"[green]OK[/green] last_close={kl[-1].close} funding_8h={d.get('funding_8h')} oi={d.get('open_interest')}")
    except Exception as e:
        print(f"[yellow]FAIL[/yellow] {e}")

    print("\n[bold]Binance Futures candles[/bold]")
    try:
        b = BinanceFuturesProvider(symbol=sym)
        kl = b.klines(interval=tf, limit=5)
        print(f"[green]OK[/green] last_close={kl[-1].close}")
    except Exception as e:
        print(f"[yellow]FAIL[/yellow] {e}")

    print("\n[bold]OKX swap candles + derivatives[/bold]")
    try:
        o = OkxSwapProvider(instrument=sym)
        kl = o.klines(interval=tf, limit=5)
        d = o.snapshot_derivatives()
        print(f"[green]OK[/green] instId={d.get('inst_id', 'BTC-USDT-SWAP')} last_close={kl[-1].close} funding_8h={d.get('funding_8h')} oi={d.get('open_interest')} errors={d.get('errors')}")
    except Exception as e:
        print(f"[yellow]FAIL[/yellow] {e}")

    print("\n[bold]Kraken spot candles[/bold]")
    try:
        k = KrakenSpotProvider(instrument=sym)
        kl = k.klines(interval=tf, limit=5)
        print(f"[green]OK[/green] last_close={kl[-1].close}")
    except Exception as e:
        print(f"[yellow]FAIL[/yellow] {e}")

    print("\n[bold]Bybit derivatives snapshot[/bold]")
    try:
        y = BybitDerivativesProvider(symbol=sym)
        d = y.snapshot_derivatives()
        print(f"[green]OK[/green] funding_8h={d.get('funding_8h')} oi={d.get('open_interest')} errors={d.get('errors')}")
    except Exception as e:
        print(f"[yellow]FAIL[/yellow] {e}")


@app.command()
def run_mock(steps: int = 200, seed: int = 7, cfg: str = "config/default.json", journal: str = "data/paper_journal.jsonl"):
    c = load_cfg(cfg)
    provider = MockProvider(seed=seed, start=100_000.0)
    sup = Supervisor(provider=provider, cfg=c, journal_path=journal)

    state = State(instrument=c["instrument"], timeframe=c["timeframe"])
    candles = provider.history(steps)

    for i, mc in enumerate(candles, start=1):
        candle = Candle(ts=mc.ts, open=mc.open, high=mc.high, low=mc.low, close=mc.close, volume=mc.volume)
        state = sup.step(state, candle)
        if i % 25 == 0:
            px = state.market_context.get("price")
            print(f"[{i}/{steps}] price={px:,.0f} setup={state.setup.get('name')} trade_id={state.trade_id}")

    print(f"[green]Done[/green]. Journal: {journal}")


@app.command()
def run_live_history(limit: int = 500, cfg: str = "config/default.json", journal: str = "data/paper_journal.jsonl"):
    c = load_cfg(cfg)

    provider = None
    kl = None

    # Try Bitunix first (fastest, no rate limits)
    try:
        provider = BitunixFuturesProvider(symbol=c["instrument"], allowed_symbols={c["instrument"]})
        kl = provider.klines(interval=c["timeframe"], limit=limit)
        print("[green]Using Bitunix Futures candles + derivatives.[/green]")
    except Exception as e:
        print(f"[yellow]Bitunix Futures failed:[/yellow] {e}")

        try:
            provider = BinanceFuturesProvider(symbol=c["instrument"])
            kl = provider.klines(interval=c["timeframe"], limit=limit)
            print("[green]Using Binance Futures candles + derivatives.[/green]")
        except Exception as e2:
            print(f"[yellow]Binance Futures failed:[/yellow] {e2}")

            try:
                provider = OkxSwapProvider(instrument=c["instrument"])
                kl = provider.klines(interval=c["timeframe"], limit=limit)
                print("[green]Using OKX swap candles + derivatives snapshot.[/green]")
            except Exception as e3:
                print(f"[yellow]OKX swap failed, falling back to Kraken spot candles.[/yellow] {e3}")

                try:
                    candle_src = KrakenSpotProvider(instrument=c["instrument"])
                    deriv_src = OkxSwapProvider(instrument=c["instrument"])
                    provider = CompositeProvider(candles_provider=candle_src, derivatives_provider=deriv_src)
                    kl = provider.klines(interval=c["timeframe"], limit=limit)
                    print("[green]Using Kraken spot candles + OKX derivatives snapshot.[/green]")
                except Exception as e4:
                    print(f"[yellow]Kraken+OKX failed, last resort: Kraken + Bybit derivatives.[/yellow] {e4}")
                    candle_src = KrakenSpotProvider(instrument=c["instrument"])
                    deriv_src = BybitDerivativesProvider(symbol=c["instrument"])
                    provider = CompositeProvider(candles_provider=candle_src, derivatives_provider=deriv_src)
                    kl = provider.klines(interval=c["timeframe"], limit=limit)
                    print("[green]Using Kraken spot candles + Bybit derivatives snapshot.[/green]")

    sup = Supervisor(provider=provider, cfg=c, journal_path=journal)
    state = State(instrument=c["instrument"], timeframe=c["timeframe"])

    for i, k in enumerate(kl, start=1):
        candle = Candle(ts=k.ts, open=k.open, high=k.high, low=k.low, close=k.close, volume=k.volume)
        state = sup.step(state, candle)
        if i % 50 == 0:
            px = state.market_context.get("price")
            d = state.derivatives or {}
            funding = d.get("funding_8h")
            oi = d.get("open_interest")
            cached = d.get("cached")
            print(f"[{i}/{len(kl)}] price={px:,.0f} funding_8h={funding} oi={oi} cached={cached} setup={state.setup.get('name')} trade_id={state.trade_id}")

    print(f"[green]Done[/green]. Journal: {journal}")


@app.command()
def report(journal: str = "data/paper_journal.jsonl", out_dir: str = "data/reports"):
    """Generate a backtest report + CSV into data/reports/ (permanent on disk)."""
    from .reporting import write_report
    paths = write_report(journal_path=journal, out_dir=out_dir)
    print(f"[green]Wrote report[/green]: {paths['md']}")
    print(f"[green]Wrote trades CSV[/green]: {paths['csv']}")


@app.command()
def journal_tail(n: int = 10, journal: str = "data/paper_journal.jsonl"):
    from .trading import PaperJournal
    j = PaperJournal(journal)
    for e in j.last(n):
        print(e)


if __name__ == "__main__":
    app()
