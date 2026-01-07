from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict, Any


@dataclass(frozen=True)
class Candle:
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class BinanceFuturesProvider:
    """Public endpoints for USDT-margined Binance Futures.
    NOTE: requires `pip install httpx` only if you use this provider.
    """

    BASE = "https://fapi.binance.com"

    def __init__(self, symbol: str = "BTCUSDT") -> None:
        self.symbol = symbol

    def klines(self, interval: str = "5m", limit: int = 500) -> List[Candle]:
        import httpx  # lazy import

        url = f"{self.BASE}/fapi/v1/klines"
        params = {"symbol": self.symbol, "interval": interval, "limit": limit}
        with httpx.Client(timeout=20) as c:
            r = c.get(url, params=params)
            r.raise_for_status()
            data = r.json()

        out: List[Candle] = []
        for k in data:
            # kline open time is ms
            ts = int(k[0])
            out.append(
                Candle(
                    ts=str(ts),
                    open=float(k[1]),
                    high=float(k[2]),
                    low=float(k[3]),
                    close=float(k[4]),
                    volume=float(k[5]),
                )
            )
        return out

    def funding_8h(self) -> Optional[float]:
        import httpx  # lazy import

        # premiumIndex includes lastFundingRate
        url = f"{self.BASE}/fapi/v1/premiumIndex"
        params = {"symbol": self.symbol}
        with httpx.Client(timeout=20) as c:
            r = c.get(url, params=params)
            r.raise_for_status()
            j = r.json()
        try:
            return float(j.get("lastFundingRate"))
        except Exception:
            return None

    def open_interest(self) -> Optional[float]:
        import httpx  # lazy import

        url = f"{self.BASE}/fapi/v1/openInterest"
        params = {"symbol": self.symbol}
        with httpx.Client(timeout=20) as c:
            r = c.get(url, params=params)
            r.raise_for_status()
            j = r.json()
        try:
            return float(j.get("openInterest"))
        except Exception:
            return None

    def snapshot_derivatives(self) -> Dict[str, Any]:
        return {
            "funding_8h": self.funding_8h(),
            "open_interest": self.open_interest(),
            "basis": None,
            "liq_map": None
        }
