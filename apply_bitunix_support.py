from __future__ import annotations

from pathlib import Path
import textwrap

FILES: dict[str, str] = {}

FILES["src/laptop_agents/data/providers/bitunix_futures.py"] = r"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx

# Bitunix Futures REST primary domain is documented as https://fapi.bitunix.com
# Market endpoints used:
# - GET /api/v1/futures/market/kline
# - GET /api/v1/futures/market/funding_rate
# - GET /api/v1/futures/market/tickers
# - GET /api/v1/futures/market/trading_pairs


def _now_ms() -> int:
    return int(time.time() * 1000)


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _minified_json(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def build_query_string(params: Optional[Dict[str, Any]]) -> str:
    \"\"\"Sort params by ASCII key, then concat key+value with NO separators.\"\"\"
    if not params:
        return ""
    items = sorted(params.items(), key=lambda kv: kv[0])
    return "".join([str(k) + str(v) for k, v in items])


def sign_rest(*, nonce: str, timestamp_ms: int, api_key: str, secret_key: str, query_params: str, body: str) -> str:
    \"\"\"Bitunix REST signature: digest=sha256(nonce+timestamp+apiKey+queryParams+body); sign=sha256(digest+secretKey).\"\"\"
    digest = _sha256_hex(nonce + str(timestamp_ms) + api_key + query_params + body)
    return _sha256_hex(digest + secret_key)


def sign_ws(*, nonce: str, timestamp_ms: int, api_key: str, secret_key: str, params_string: str) -> str:
    \"\"\"Bitunix WS signature: digest=sha256(nonce+timestamp+apiKey+params); sign=sha256(digest+secretKey).\"\"\"
    digest = _sha256_hex(nonce + str(timestamp_ms) + api_key + params_string)
    return _sha256_hex(digest + secret_key)


@dataclass(frozen=True)
class Candle:
    ts: int  # milliseconds unix time
    open: float
    high: float
    low: float
    close: float
    vol: float | None = None


class BitunixFuturesProvider:
    \"\"\"Public-market-data provider for Bitunix Futures.

    Notes:
    - This is intentionally *public only* so you can get unblocked candles immediately.
    - We include signing helpers here so adding live trading later is trivial.
    \"\"\"

    BASE_URL = "https://fapi.bitunix.com"

    def __init__(self, *, symbol: str, allowed_symbols: Optional[Iterable[str]] = None, timeout_s: float = 20.0):
        self.symbol = symbol
        self.allowed_symbols = set(allowed_symbols) if allowed_symbols else {symbol}
        self.timeout_s = timeout_s
        self._assert_allowed()

    def _assert_allowed(self) -> None:
        if self.symbol not in self.allowed_symbols:
            raise ValueError(f"Symbol '{self.symbol}' not allowed. Allowed: {sorted(self.allowed_symbols)}")

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = self.BASE_URL + path
        headers = {"User-Agent": "btc-laptop-agents/0.1"}
        with httpx.Client(timeout=self.timeout_s, headers=headers) as c:
            r = c.get(url, params=params)
            r.raise_for_status()
            payload = r.json()
        if isinstance(payload, dict) and payload.get("code") != 0:
            raise RuntimeError(f"Bitunix API error: {payload}")
        return payload

    def trading_pairs(self) -> List[Dict[str, Any]]:
        payload = self._get("/api/v1/futures/market/trading_pairs", params={"symbols": self.symbol})
        return payload.get("data") or []

    def tickers(self) -> List[Dict[str, Any]]:
        payload = self._get("/api/v1/futures/market/tickers", params={"symbols": self.symbol})
        return payload.get("data") or []

    def funding_rate(self) -> Optional[float]:
        payload = self._get("/api/v1/futures/market/funding_rate", params={"symbol": self.symbol})
        data = payload.get("data") or []
        if not data:
            return None
        # docs show "fundingRate" string
        fr = data[0].get("fundingRate")
        try:
            return float(fr) if fr is not None else None
        except Exception:
            return None

    def klines(self, *, interval: str, limit: int = 200, start_ms: Optional[int] = None, end_ms: Optional[int] = None) -> List[Candle]:
        # docs: limit default 100 max 200
        limit = max(1, min(int(limit), 200))
        params: Dict[str, Any] = {"symbol": self.symbol, "interval": interval, "limit": limit}
        if start_ms is not None:
            params["startTime"] = int(start_ms)
        if end_ms is not None:
            params["endTime"] = int(end_ms)

        payload = self._get("/api/v1/futures/market/kline", params=params)
        out: List[Candle] = []
        for row in payload.get("data") or []:
            # docs response: open/high/low/close/time
            ts = int(row.get("time"))
            out.append(
                Candle(
                    ts=ts,
                    open=float(row.get("open")),
                    high=float(row.get("high")),
                    low=float(row.get("low")),
                    close=float(row.get("close")),
                    vol=float(row.get("baseVol")) if row.get("baseVol") is not None else None,
                )
            )
        return out

    def klines_paged(self, *, interval: str, total: int, end_ms: Optional[int] = None) -> List[Candle]:
        \"\"\"Fetch up to 'total' most recent candles by paging backward using endTime.
        Uses public REST with max 200 per request.
        \"\"\"
        remaining = int(total)
        cursor_end = end_ms
        all_rows: List[Candle] = []

        while remaining > 0:
            batch = min(200, remaining)
            rows = self.klines(interval=interval, limit=batch, end_ms=cursor_end)
            if not rows:
                break
            # API returns ascending by time in example; we handle either.
            rows_sorted = sorted(rows, key=lambda c: c.ts)
            all_rows = rows_sorted + all_rows
            remaining -= len(rows_sorted)
            # move cursor to just before earliest candle
            earliest = rows_sorted[0].ts
            cursor_end = earliest - 1
            if len(rows_sorted) < batch:
                break

        # return chronological, trimmed to total
        all_rows = sorted(all_rows, key=lambda c: c.ts)
        if len(all_rows) > total:
            all_rows = all_rows[-total:]
        return all_rows

    def snapshot_derivatives(self) -> Dict[str, Any]:
        \"\"\"Return what the rest of your stack expects (funding + OI if available).

        Bitunix public docs expose funding rate; open interest is not documented on the public market endpoints,
        so we keep it None for now (you can add WS/extra endpoint later).
        \"\"\"
        return {
            "funding_8h": self.funding_rate(),
            "open_interest": None,
            "basis": None,
            "liq_map": None,
            "errors": [],
        }
"""

FILES["src/laptop_agents/bitunix_cli.py"] = r"""
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
    \"\"\"Quick connectivity check: trading_pairs + tickers + funding + last candle.\"\"\"
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
    \"\"\"Run your existing 5-agent pipeline over Bitunix historical candles (acts like a backtest slice).\"\"\"
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
"""

FILES["tests/test_bitunix_signing.py"] = r"""
from __future__ import annotations

import hashlib
import json

from laptop_agents.data.providers.bitunix_futures import build_query_string, sign_rest


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def test_query_string_ascii_sorted_concat():
    # docs example shows: id1uid200
    qs = build_query_string({"uid": 200, "id": 1})
    assert qs == "id1uid200"


def test_rest_signature_matches_reference_computation():
    nonce = "123456"
    timestamp_ms = 1724285700000
    api_key = "yourApiKey"
    secret_key = "yourSecretKey"
    query_params = build_query_string({"uid": 200, "id": 1})

    body_obj = {"uid": "2899", "arr": [{"id": 1, "name": "maple"}, {"id": 2, "name": "lily"}]}
    body = json.dumps(body_obj, separators=(",", ":"), ensure_ascii=False)

    # expected per docs: digest=sha256(nonce+timestamp+apiKey+queryParams+body); sign=sha256(digest+secretKey)
    digest = sha256_hex(nonce + str(timestamp_ms) + api_key + query_params + body)
    expected = sha256_hex(digest + secret_key)

    got = sign_rest(
        nonce=nonce,
        timestamp_ms=timestamp_ms,
        api_key=api_key,
        secret_key=secret_key,
        query_params=query_params,
        body=body,
    )
    assert got == expected
"""

FILES["config/bitunix_btcusd_5m.json"] = r"""
{
  "instrument": "BTCUSD",
  "timeframe": "5m",
  "risk": { "equity": 10000.0, "risk_pct": 0.01, "rr_min": 1.8 },
  "derivatives_gates": { "half_size_funding_8h": 0.0003, "no_trade_funding_8h": 0.001 },
  "setups": {
    "pullback_ribbon": { "enabled": true, "ema_fast": 20, "ema_slow": 50, "entry_band_pct": 0.0015, "stop_atr_mult": 1.2, "tp_r_mult": 1.8 },
    "sweep_invalidation": { "enabled": true, "eq_tolerance_pct": 0.0008, "lookback": 40, "tp_r_mult": 2.0 }
  }
}
"""

def _write(path: str, content: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    normalized = textwrap.dedent(content).lstrip("\n").rstrip() + "\n"
    p.write_text(normalized, encoding="utf-8")

def main() -> None:
    for path, content in FILES.items():
        _write(path, content)
    print("Patch applied: Bitunix provider + Bitunix CLI + signing tests + config.")

if __name__ == "__main__":
    main()
