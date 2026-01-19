from __future__ import annotations
from typing import Any, Dict


class CompositeProvider:
    """Combine a candle provider + a derivatives provider under one interface."""

    def __init__(
        self, candles_provider: Any, derivatives_provider: Any | None = None
    ) -> None:
        self.candles_provider = candles_provider
        self.derivatives_provider = derivatives_provider

    def klines(self, interval: str = "5m", limit: int = 500):
        return self.candles_provider.klines(interval=interval, limit=limit)

    def snapshot_derivatives(self) -> Dict[str, Any]:
        if self.derivatives_provider is None:
            return {
                "funding_8h": None,
                "open_interest": None,
                "basis": None,
                "liq_map": None,
            }
        return self.derivatives_provider.snapshot_derivatives()
