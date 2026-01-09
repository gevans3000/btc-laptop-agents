from __future__ import annotations

from typing import Any, Dict

from .state import State


class RiskGateAgent:
    """Agent Risk Gate — Enforce safety constraints (funding, max risk, etc.)."""
    name = "risk_gate"

    def __init__(self, gate_cfg: Dict[str, Any]) -> None:
        self.cfg = gate_cfg

    def run(self, state: State) -> State:
        order = state.order
        if not order or not order.get("go"):
            return state

        # 1. Funding Gates
        # If upstream agents flagged a "NO_TRADE" condition, block it here.
        deriv = state.derivatives or {}
        flags = deriv.get("flags", [])
        
        # Check standard flags that imply "Do Not Trade"
        blockers = [f for f in flags if "NO_TRADE" in f]
        if blockers:
            state.order = {
                "go": False, 
                "reason": f"risk_gate_blocked: {', '.join(blockers)}",
                "setup": order.get("setup", {})
            }
            return state

        # 2. Max Position Risk Gate (Safety Net)
        # If the risk_pct requested is suspiciously high (e.g. > 5%), block it.
        # This protects against configuration typos (e.g. 10.0 instead of 0.01).
        risk_pct = float(order.get("risk_pct", 0.0))
        max_risk = 0.02 # Hard limit 2%
        if risk_pct > max_risk:
             state.order = {
                "go": False,
                "reason": f"risk_gate_blocked: risk_pct {risk_pct} exceeds hard limit {max_risk}",
                "setup": order.get("setup", {})
             }
             return state

        return state
