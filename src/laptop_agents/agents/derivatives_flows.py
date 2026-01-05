from __future__ import annotations

from typing import Any, Dict

from .state import State


class DerivativesFlowsAgent:
    """Agent 2 — Derivatives/Flows: funding/OI snapshot with caching."""
    name = "derivatives_flows"

    def __init__(self, provider: Any, gates: Dict[str, float], refresh_bars: int = 6) -> None:
        self.provider = provider
        self.gates = gates
        self.refresh_bars = max(1, int(refresh_bars))
        self._bar = 0
        self._last: Dict[str, Any] | None = None

    def run(self, state: State) -> State:
        self._bar += 1

        # refresh only every N bars, else reuse cached
        snap: Dict[str, Any]
        if self._last is not None and (self._bar % self.refresh_bars) != 0:
            snap = dict(self._last)
            snap["cached"] = True
        else:
            snap = {"funding_8h": None, "open_interest": None, "basis": None, "liq_map": None}
            if hasattr(self.provider, "snapshot_derivatives"):
                try:
                    snap = self.provider.snapshot_derivatives()
                except Exception:
                    snap["error"] = "snapshot_failed"
            snap["cached"] = False
            self._last = dict(snap)

        funding = snap.get("funding_8h")
        flags = []

        if funding is None:
            flags.append("funding_missing")
        else:
            if funding >= self.gates["no_trade_funding_8h"]:
                flags.append("NO_TRADE_funding_hot")
            elif funding >= self.gates["half_size_funding_8h"]:
                flags.append("HALF_SIZE_funding_warm")

        state.derivatives = {**snap, "flags": flags, "gates": self.gates}
        return state
