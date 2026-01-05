from __future__ import annotations

from pathlib import Path
import textwrap

FILES: dict[str, str] = {

"src/laptop_agents/data/providers/kraken_spot.py": r'''
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional


@dataclass(frozen=True)
class Candle:
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class KrakenSpotProvider:
    """Kraken public OHLC (spot) as a US-friendly candle source."""

    BASE = "https://api.kraken.com/0/public/OHLC"

    def __init__(self, instrument: str = "BTCUSDT") -> None:
        self.instrument = instrument

    def klines(self, interval: str = "5m", limit: int = 500) -> List[Candle]:
        import httpx  # lazy import

        iv = _parse_interval_minutes(interval)
        candidates = _pair_candidates(self.instrument)

        last_err: Optional[str] = None
        for pair in candidates:
            params = {"pair": pair, "interval": iv}
            try:
                with httpx.Client(timeout=20) as c:
                    r = c.get(self.BASE, params=params)
                    r.raise_for_status()
                    j = r.json()

                if j.get("error"):
                    last_err = str(j["error"])
                    continue

                result = j.get("result", {})
                keys = [k for k in result.keys() if k != "last"]
                if not keys:
                    last_err = "no_result_keys"
                    continue

                rows = result[keys[0]]
                if not rows:
                    last_err = "empty_rows"
                    continue

                # drop the most recent partial candle
                if len(rows) > 1:
                    rows = rows[:-1]

                rows = rows[-limit:]
                out: List[Candle] = []
                for row in rows:
                    ts_sec = int(row[0])
                    ts_iso = datetime.fromtimestamp(ts_sec, tz=timezone.utc).isoformat()
                    out.append(
                        Candle(
                            ts=ts_iso,
                            open=float(row[1]),
                            high=float(row[2]),
                            low=float(row[3]),
                            close=float(row[4]),
                            volume=float(row[6]),
                        )
                    )
                return out
            except Exception as e:
                last_err = str(e)
                continue

        raise RuntimeError(f"Kraken OHLC failed for all pair candidates. Last error: {last_err}")


def _parse_interval_minutes(interval: str) -> int:
    s = interval.strip().lower()
    if s.endswith("m"):
        return int(s[:-1])
    if s.endswith("h"):
        return int(s[:-1]) * 60
    if s.endswith("d"):
        return int(s[:-1]) * 1440
    return int(s)


def _pair_candidates(instrument: str) -> List[str]:
    ins = instrument.strip().upper()
    # Kraken commonly uses XBT instead of BTC
    if ins in ("BTCUSDT", "XBTUSDT"):
        return ["XBT/USDT", "XBTUSDT", "BTC/USDT", "BTCUSDT", "XBT/USD", "XBTUSD", "BTC/USD", "BTCUSD"]
    if ins in ("BTCUSD", "XBTUSD"):
        return ["XBT/USD", "XBTUSD", "BTC/USD", "BTCUSD"]
    if len(ins) == 6:
        return [f"{ins[:3]}/{ins[3:]}", ins]
    return [ins]
''',

"src/laptop_agents/data/providers/bybit_derivatives.py": r'''
from __future__ import annotations

from typing import Dict, Any


class BybitDerivativesProvider:
    """Public Bybit V5 tickers for linear perp metrics (funding + OI)."""

    BASE = "https://api.bybit.com"

    def __init__(self, symbol: str = "BTCUSDT") -> None:
        self.symbol = symbol

    def snapshot_derivatives(self) -> Dict[str, Any]:
        import httpx  # lazy import

        url = f"{self.BASE}/v5/market/tickers"
        params = {"category": "linear", "symbol": self.symbol}
        out: Dict[str, Any] = {"funding_8h": None, "open_interest": None, "basis": None, "liq_map": None}

        try:
            with httpx.Client(timeout=20) as c:
                r = c.get(url, params=params)
                r.raise_for_status()
                j = r.json()

            lst = (((j.get("result") or {}).get("list")) or [])
            if not lst:
                out["error"] = "empty_tickers"
                return out

            x = lst[0]
            out["funding_8h"] = float(x.get("fundingRate")) if x.get("fundingRate") is not None else None
            out["open_interest"] = float(x.get("openInterest")) if x.get("openInterest") is not None else None
            return out
        except Exception as e:
            out["error"] = f"bybit_snapshot_failed: {e}"
            return out
''',

"src/laptop_agents/data/providers/composite.py": r'''
from __future__ import annotations
from typing import Any, Dict


class CompositeProvider:
    """Combine a candle provider + a derivatives provider under one interface."""

    def __init__(self, candles_provider: Any, derivatives_provider: Any | None = None) -> None:
        self.candles_provider = candles_provider
        self.derivatives_provider = derivatives_provider

    def klines(self, interval: str = "5m", limit: int = 500):
        return self.candles_provider.klines(interval=interval, limit=limit)

    def snapshot_derivatives(self) -> Dict[str, Any]:
        if self.derivatives_provider is None:
            return {"funding_8h": None, "open_interest": None, "basis": None, "liq_map": None}
        return self.derivatives_provider.snapshot_derivatives()
''',

"src/laptop_agents/data/providers/__init__.py": r'''
from .mock import MockProvider
from .binance_futures import BinanceFuturesProvider
from .kraken_spot import KrakenSpotProvider
from .bybit_derivatives import BybitDerivativesProvider
from .composite import CompositeProvider

__all__ = [
    "MockProvider",
    "BinanceFuturesProvider",
    "KrakenSpotProvider",
    "BybitDerivativesProvider",
    "CompositeProvider",
]
''',

# Size down if funding missing (provisional mode)
"src/laptop_agents/agents/execution_risk.py": r'''
from __future__ import annotations

from typing import Any, Dict, Optional

from .state import State


class ExecutionRiskSentinelAgent:
    """Agent 4 — Execution & Risk Sentinel: GO/NO-GO + exact order."""
    name = "execution_risk_sentinel"

    def __init__(self, risk_cfg: Dict[str, Any]) -> None:
        self.risk_cfg = risk_cfg

    def run(self, state: State) -> State:
        setup = state.setup or {"name": "NONE"}
        deriv = state.derivatives or {}
        flags = set(deriv.get("flags", []))

        if setup.get("name") == "NONE":
            state.order = {"go": False, "reason": "no_setup"}
            return state

        size_mult = 1.0
        if "NO_TRADE_funding_hot" in flags:
            state.order = {"go": False, "reason": "funding_hot_no_trade", "setup": setup}
            return state
        if "HALF_SIZE_funding_warm" in flags:
            size_mult = 0.5
        if "funding_missing" in flags:
            size_mult = min(size_mult, 0.5)

        side = setup["side"]
        entry_type = setup.get("entry_type")
        entry: Optional[float] = None

        if entry_type == "limit":
            entry = float(setup["entry"])
        elif entry_type == "market_on_trigger":
            entry = None
        else:
            state.order = {"go": False, "reason": "unknown_entry_type", "setup": setup}
            return state

        sl = float(setup["sl"])
        tp = float(setup["tp"])

        rr_min = float(self.risk_cfg["rr_min"])
        equity = float(self.risk_cfg["equity"])
        risk_pct = float(self.risk_cfg["risk_pct"])

        state.order = {
            "go": True,
            "pending_trigger": entry is None,
            "side": side,
            "entry_type": "limit" if entry is not None else "market",
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "rr_min": rr_min,
            "size_mult": size_mult,
            "risk_pct": risk_pct,
            "equity": equity,
            "setup": setup,
        }
        return state
''',

# CLI fallback: Binance (if works) else Kraken candles + Bybit derivatives
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

    try:
        provider = BinanceFuturesProvider(symbol=c["instrument"])
        kl = provider.klines(interval=c["timeframe"], limit=limit)
        print("[green]Using Binance Futures candles + derivatives.[/green]")
    except Exception as e:
        msg = str(e)
        if " 451 " in msg or "status code 451" in msg:
            print("[yellow]Binance Futures blocked (HTTP 451). Falling back to Kraken candles + Bybit funding/OI.[/yellow]")
        else:
            print(f"[yellow]Binance Futures failed. Falling back to Kraken candles + Bybit funding/OI. Error: {e}[/yellow]")

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
            funding = (state.derivatives or {}).get("funding_8h")
            print(f"[{i}/{len(kl)}] price={px:,.0f} funding_8h={funding} setup={state.setup.get('name')} trade_id={state.trade_id}")

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
    print("Patch applied: Kraken+Bybit fallback + half-size on missing funding.")

if __name__ == "__main__":
    main()
