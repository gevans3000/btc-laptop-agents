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
