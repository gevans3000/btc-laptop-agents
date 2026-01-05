from __future__ import annotations

from pathlib import Path
import textwrap

FILES: dict[str, str] = {

"src/laptop_agents/data/providers/okx_swap.py": r'''
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class Candle:
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class OkxSwapProvider:
    """OKX public swap (perp) candles + derivatives snapshot."""

    BASE = "https://www.okx.com"

    def __init__(self, instrument: str = "BTCUSDT") -> None:
        self.instrument = instrument
        self.inst_id = _to_okx_swap_inst_id(instrument)

    def klines(self, interval: str = "5m", limit: int = 500) -> List[Candle]:
        import httpx  # lazy import

        url = f"{self.BASE}/api/v5/market/history-candles"
        params = {"instId": self.inst_id, "bar": interval, "limit": limit}

        with httpx.Client(timeout=20) as c:
            r = c.get(url, params=params)
            r.raise_for_status()
            j = r.json()

        if j.get("code") != "0":
            raise RuntimeError(f"OKX history-candles error: {j}")

        rows = j.get("data") or []
        if not rows:
            raise RuntimeError("OKX history-candles returned empty data")

        # OKX returns newest -> oldest; reverse to chronological
        out: List[Candle] = []
        for row in reversed(rows):
            ts_ms = int(row[0])
            ts_iso = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat()
            out.append(
                Candle(
                    ts=ts_iso,
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                )
            )
        return out

    def snapshot_derivatives(self) -> Dict[str, Any]:
        """
        Returns:
          funding_8h: float | None
          open_interest: float | None   (contracts)
          basis: None (placeholder)
          liq_map: None (placeholder)
          errors: list[str]
        """
        import httpx  # lazy import

        out: Dict[str, Any] = {
            "funding_8h": None,
            "open_interest": None,
            "basis": None,
            "liq_map": None,
            "errors": [],
            "source": "okx",
            "inst_id": self.inst_id,
        }

        # Funding rate
        try:
            url = f"{self.BASE}/api/v5/public/funding-rate"
            params = {"instId": self.inst_id}
            with httpx.Client(timeout=20) as c:
                r = c.get(url, params=params)
                r.raise_for_status()
                j = r.json()

            if j.get("code") == "0" and (j.get("data") or []):
                out["funding_8h"] = float(j["data"][0]["fundingRate"])
            else:
                out["errors"].append(f"funding_bad_payload:{j}")
        except Exception as e:
            out["errors"].append(f"funding_failed:{e}")

        # Open interest
        oi = _okx_open_interest(self.inst_id)
        if oi is None:
            out["errors"].append("open_interest_missing")
        else:
            out["open_interest"] = oi

        return out


def _okx_open_interest(inst_id: str) -> Optional[float]:
    import httpx  # lazy import

    base = "https://www.okx.com/api/v5/public/open-interest"

    # Try with instId first
    try:
        with httpx.Client(timeout=20) as c:
            r = c.get(base, params={"instType": "SWAP", "instId": inst_id})
            r.raise_for_status()
            j = r.json()
        if j.get("code") == "0" and (j.get("data") or []):
            row = j["data"][0]
            oi = row.get("oi")
            return float(oi) if oi is not None else None
    except Exception:
        pass

    # Fallback: pull all SWAP and filter
    try:
        with httpx.Client(timeout=20) as c:
            r = c.get(base, params={"instType": "SWAP"})
            r.raise_for_status()
            j = r.json()
        if j.get("code") == "0" and (j.get("data") or []):
            for row in j["data"]:
                if row.get("instId") == inst_id:
                    oi = row.get("oi")
                    return float(oi) if oi is not None else None
    except Exception:
        return None

    return None


def _to_okx_swap_inst_id(instrument: str) -> str:
    ins = instrument.strip().upper()
    if ins in ("BTCUSDT", "XBTUSDT"):
        return "BTC-USDT-SWAP"
    if ins in ("BTCUSD", "XBTUSD"):
        return "BTC-USD-SWAP"
    if len(ins) == 6:
        return f"{ins[:3]}-{ins[3:]}-SWAP"
    return f"{ins}-SWAP"
''',

"src/laptop_agents/data/providers/bybit_derivatives.py": r'''
from __future__ import annotations

from typing import Any, Dict


class BybitDerivativesProvider:
    """Public Bybit V5 tickers for linear perp metrics (funding + OI)."""

    BASE = "https://api.bybit.com"

    def __init__(self, symbol: str = "BTCUSDT") -> None:
        self.symbol = symbol.strip().upper()

    def snapshot_derivatives(self) -> Dict[str, Any]:
        import httpx  # lazy import

        url = f"{self.BASE}/v5/market/tickers"
        params = {"category": "linear", "symbol": self.symbol}

        out: Dict[str, Any] = {
            "funding_8h": None,
            "open_interest": None,
            "basis": None,
            "liq_map": None,
            "errors": [],
            "source": "bybit",
        }

        try:
            with httpx.Client(timeout=20) as c:
                r = c.get(url, params=params)
                r.raise_for_status()
                j = r.json()

            # Expected: retCode=0, result.list[0].fundingRate/openInterest
            if j.get("retCode") != 0:
                out["errors"].append(f"retCode={j.get('retCode')} retMsg={j.get('retMsg')}")
                return out

            lst = (((j.get("result") or {}).get("list")) or [])
            if not lst:
                out["errors"].append("empty_list")
                return out

            x = lst[0]
            fr = x.get("fundingRate")
            oi = x.get("openInterest")

            try:
                out["funding_8h"] = float(fr) if fr not in (None, "") else None
            except Exception:
                out["errors"].append(f"bad_fundingRate={fr!r}")

            try:
                out["open_interest"] = float(oi) if oi not in (None, "") else None
            except Exception:
                out["errors"].append(f"bad_openInterest={oi!r}")

            return out

        except Exception as e:
            out["errors"].append(f"request_failed:{e}")
            return out
''',

"src/laptop_agents/data/providers/__init__.py": r'''
from .mock import MockProvider
from .binance_futures import BinanceFuturesProvider
from .kraken_spot import KrakenSpotProvider
from .bybit_derivatives import BybitDerivativesProvider
from .composite import CompositeProvider
from .okx_swap import OkxSwapProvider

__all__ = [
    "MockProvider",
    "BinanceFuturesProvider",
    "KrakenSpotProvider",
    "BybitDerivativesProvider",
    "CompositeProvider",
    "OkxSwapProvider",
]
''',

"src/laptop_agents/cli.py": r'''
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
)
from .indicators import Candle

app = typer.Typer(help="BTC Laptop Agents — 5-agent paper trading loop (5m)")


def load_cfg(path: str = "config/default.json") -> dict:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


@app.command()
def agents():
    print("- market_intake")
    print("- derivatives_flows")
    print("- setup_signal")
    print("- execution_risk_sentinel")
    print("- journal_coach")


@app.command()
def debug_feeds(cfg: str = "config/default.json"):
    """Quick connectivity + payload sanity checks for each feed."""
    c = load_cfg(cfg)
    sym = c["instrument"]
    tf = c["timeframe"]

    print("[bold]Binance Futures candles[/bold]")
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
        print(f"[green]OK[/green] instId={d.get('inst_id')} last_close={kl[-1].close} funding_8h={d.get('funding_8h')} oi={d.get('open_interest')} errors={d.get('errors')}")
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

    # 1) Try Binance Futures (often blocked with 451 for some regions)
    try:
        provider = BinanceFuturesProvider(symbol=c["instrument"])
        kl = provider.klines(interval=c["timeframe"], limit=limit)
        print("[green]Using Binance Futures candles + derivatives.[/green]")
    except Exception as e:
        print(f"[yellow]Binance Futures failed:[/yellow] {e}")

        # 2) Prefer OKX swap (perp) for BOTH candles + derivatives
        try:
            provider = OkxSwapProvider(instrument=c["instrument"])
            kl = provider.klines(interval=c["timeframe"], limit=limit)
            print("[green]Using OKX swap candles + derivatives snapshot.[/green]")
        except Exception as e2:
            print(f"[yellow]OKX swap failed, falling back to Kraken spot candles.[/yellow] {e2}")

            # 3) Kraken candles + OKX derivatives snapshot
            try:
                candle_src = KrakenSpotProvider(instrument=c["instrument"])
                deriv_src = OkxSwapProvider(instrument=c["instrument"])
                provider = CompositeProvider(candles_provider=candle_src, derivatives_provider=deriv_src)
                kl = provider.klines(interval=c["timeframe"], limit=limit)
                print("[green]Using Kraken spot candles + OKX derivatives snapshot.[/green]")
            except Exception as e3:
                print(f"[yellow]Kraken+OKX failed, last resort: Kraken + Bybit derivatives.[/yellow] {e3}")
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
            print(f"[{i}/{len(kl)}] price={px:,.0f} funding_8h={funding} oi={oi} setup={state.setup.get('name')} trade_id={state.trade_id}")

    print(f"[green]Done[/green]. Journal: {journal}")


@app.command()
def journal_tail(n: int = 10, journal: str = "data/paper_journal.jsonl"):
    from .trading import PaperJournal
    j = PaperJournal(journal)
    for e in j.last(n):
        print(e)


if __name__ == "__main__":
    app()
''',
}

def _write(path: str, content: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    normalized = textwrap.dedent(content).lstrip("\n").rstrip() + "\n"
    p.write_text(normalized, encoding="utf-8")

def main() -> None:
    for path, content in FILES.items():
        _write(path, content)
    print("Patch applied: OKX swap feed + debug-feeds + stronger derivatives parsing.")

if __name__ == "__main__":
    main()
