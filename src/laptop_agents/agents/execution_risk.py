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
        elif entry_type == "market":
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
