from __future__ import annotations

"""
Supervisor: Orchestrates the linear agent pipeline and interfaces with the broker.

Part of the Supervisor pipeline. See ENGINEER.md Section 4 for pipeline order.
"""

from typing import Any, Dict, Optional

from ..indicators import Candle
from ..paper import PaperBroker
from .state import State
from .market_intake import MarketIntakeAgent
from .derivatives_flows import DerivativesFlowsAgent
from .setup_signal import SetupSignalAgent
from .execution_risk import ExecutionRiskSentinelAgent
from .cvd_divergence import CvdDivergenceAgent
from .journal_coach import JournalCoachAgent
from .risk_gate import RiskGateAgent


class Supervisor:
    """
    The Supervisor orchestrates the linear agent pipeline.

    It is responsible for:
    1. Initializing all sub-agents.
    2. Managing the shared `State` object transition through the pipeline.
    3. Ensuring the sequence: Data -> Context -> Signal -> Risk -> Execution -> Logging.
    4. Interfacing with the Broker for final execution.

    The pipeline is strictly synchronous and deterministic per step.
    """

    def __init__(
        self,
        provider: Any,
        cfg: Dict[str, Any],
        journal_path: str = "data/paper_journal.jsonl",
        broker: Optional[Any] = None,
        instrument_info: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.provider = provider
        self.cfg = cfg
        self.broker = broker or PaperBroker()

        engine = cfg.get("engine", {})
        self.pending_trigger_max_bars = int(engine.get("pending_trigger_max_bars", 24))
        self.min_history_bars = int(engine.get("min_history_bars", 100))
        refresh_bars = int(engine.get("derivatives_refresh_bars", 6))

        self.a1 = MarketIntakeAgent()
        self.a2 = DerivativesFlowsAgent(
            provider, cfg["derivatives_gates"], refresh_bars=refresh_bars
        )
        self.a3 = SetupSignalAgent(cfg["setups"])
        self.cvd_agent = CvdDivergenceAgent(cfg.get("cvd", {}))
        self.a4 = ExecutionRiskSentinelAgent(
            cfg["risk"], instrument_info=instrument_info
        )
        self.risk_gate = RiskGateAgent(
            cfg.get("risk", {})
        )  # Use risk cfg for max_risk checks
        self.a5 = JournalCoachAgent(journal_path)

    def step(self, state: State, candle: Candle, skip_broker: bool = False) -> State:
        state.candles.append(candle)
        # Keep enough for the warmup plus some buffer, or at least 800
        max_keep = max(800, self.min_history_bars + 100)
        state.candles = state.candles[-max_keep:]

        # A1..A4 produce an order (or pending trigger)
        state = self.a1.run(state)
        state = self.a2.run(state)
        state = self.cvd_agent.run(state)
        state = self.a3.run(state)
        state = self.a4.run(state)

        # pending-trigger lifecycle (time stop)
        cancels = []
        if state.order.get("go") and state.order.get("pending_trigger"):
            state.pending_trigger_bars += 1
            if state.pending_trigger_bars >= self.pending_trigger_max_bars:
                cancels.append(
                    {
                        "reason": "pending_trigger_expired",
                        "bars": state.pending_trigger_bars,
                        "at": candle.ts,
                    }
                )
                # stop trying until next setup changes (journal agent will reset trade_id)
                state.order = {"go": False, "reason": "pending_trigger_expired"}
        else:
            state.pending_trigger_bars = 0

        # Resolve trigger -> market entry if needed
        order = self._resolve_order(state, candle)
        state.order = (
            order or {}
        )  # _resolve_order returns Optional[Dict], ensure it's not None

        # GATE: Check strict risk constraints before broker sees the order
        state = self.risk_gate.run(state)
        order = state.order  # Refresh order in case Gate blocked it

        # Broker handles fills/exits
        if skip_broker:
            broker_events = {"fills": [], "exits": [], "errors": [], "cancels": cancels}
        else:
            broker_events = self.broker.on_candle(candle, order)
            broker_events["cancels"] = cancels

        state.broker_events = broker_events

        # Journal/Coach logs everything + resets trade_id on exit/cancel
        state = self.a5.run(state)
        return state

    def _resolve_order(self, state: State, candle: Candle) -> Optional[Dict[str, Any]]:
        order = dict(state.order or {})
        if not order.get("go"):
            return None

        setup = order.get("setup", {})
        risk_dollars = (
            float(order["equity"])
            * float(order["risk_pct"])
            * float(order["size_mult"])
        )

        # Market-on-trigger sweep logic (scaffold)
        if setup.get("entry_type") == "market_on_trigger":
            trig = setup.get("trigger", {})
            if trig.get("type") == "sweep_and_close_back_below":
                lvl = float(trig["level"])
                tol = float(trig["tol"])
                if candle.high > (lvl + tol) and candle.close < lvl:
                    entry = float(candle.close)
                else:
                    return None
            elif trig.get("type") == "sweep_and_close_back_above":
                lvl = float(trig["level"])
                tol = float(trig["tol"])
                if candle.low < (lvl - tol) and candle.close > lvl:
                    entry = float(candle.close)
                else:
                    return None
            else:
                return None
            order["entry_type"] = "market"
            order["entry"] = entry

        if order["entry_type"] == "market" and order["entry"] is None:
            entry = float(candle.close)
            order["entry"] = entry
        else:
            entry = float(order["entry"])
        sl = float(order["sl"])
        tp = float(order["tp"])

        stop_dist = abs(entry - sl)
        if stop_dist <= 0:
            return None

        rr = abs(tp - entry) / stop_dist
        if rr < float(order["rr_min"]):
            return None

        qty = risk_dollars / stop_dist

        # --- HARD LIMIT ENFORCEMENT ---
        from laptop_agents import constants as hard_limits

        # 1. Cap by absolute Max Position Size ($)
        max_notional_abs = hard_limits.MAX_POSITION_SIZE_USD
        max_qty_abs = max_notional_abs / entry if entry > 0 else 0.0

        # 2. Cap by Max Leverage (x)
        max_notional_lev = float(order["equity"]) * hard_limits.MAX_LEVERAGE
        max_qty_lev = max_notional_lev / entry if entry > 0 else 0.0

        # Final capped qty
        qty = min(qty, max_qty_abs, max_qty_lev)

        # Enforce Lot Step
        lot_step = float(order.get("lot_step", 0.001))
        qty = int(qty / lot_step) * lot_step

        # Enforce Min Notional
        min_notional = float(order.get("min_notional", 5.0))
        if (qty * entry) < min_notional:
            return None

        return {
            "go": True,
            "side": order["side"],
            "entry_type": order["entry_type"],
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "qty": qty,
            "rr": rr,
            "setup": setup.get("name"),
        }
