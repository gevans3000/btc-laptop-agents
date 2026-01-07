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
