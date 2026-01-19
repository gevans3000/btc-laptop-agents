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
                out["errors"].append(
                    f"retCode={j.get('retCode')} retMsg={j.get('retMsg')}"
                )
                return out

            lst = ((j.get("result") or {}).get("list")) or []
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
