from __future__ import annotations

"""
JournalCoachAgent: Log plan, fills, exits and provide coaching feedback.

Part of the Supervisor pipeline. See ENGINEER.md Section 4 for pipeline order.
"""

from typing import Any, Dict

from ..trading import PaperJournal
from .state import State


class JournalCoachAgent:
    """Agent 5 — Journal & Coach: log plan + fills + exits, extract rule notes."""

    name = "journal_coach"

    def __init__(self, journal_path: str = "data/paper_journal.jsonl") -> None:
        self.j = PaperJournal(journal_path)

    def run(self, state: State) -> State:
        cancels = (state.broker_events or {}).get("cancels", [])
        fills = (state.broker_events or {}).get("fills", [])
        exits = (state.broker_events or {}).get("exits", [])

        # Create a plan record only when:
        #  - order.go is True
        #  - and this plan differs from last plan_key
        if state.trade_id is None and state.order.get("go"):
            plan_key = self._plan_key(state)
            if plan_key != state.meta.get("last_plan_key"):
                state.meta["last_plan_key"] = plan_key
                plan = {
                    "market_context": state.market_context,
                    "derivatives": state.derivatives,
                    "setup": state.setup,
                    "order": state.order,
                }
                trade_id = self.j.new_trade(
                    instrument=state.instrument,
                    timeframe=state.timeframe,
                    direction=state.order.get("side", "FLAT"),
                    plan=plan,
                )
                state.trade_id = trade_id
                self.j.add_update(
                    trade_id, {"note": "plan_created", "plan_key": plan_key}
                )

        # Log cancels (then reset to allow new plans)
        if state.trade_id and cancels:
            tid: str = state.trade_id
            for c in cancels:
                self.j.add_update(tid, {"note": "canceled", "cancel": c})
            state.trade_id = None
            state.pending_trigger_bars = 0
            return state

        # Log fills/exits
        if state.trade_id:
            tid = state.trade_id
            for f in fills:
                self.j.add_update(tid, {"note": "fill", "fill": f})
            for x in exits:
                coach_note = self._coach_note(x)
                self.j.add_update(tid, {"note": "exit", "exit": x, "coach": coach_note})
                # trade closed -> reset for next opportunity
                state.trade_id = None
                state.pending_trigger_bars = 0

        return state

    def _plan_key(self, state: State) -> str:
        s = state.setup or {}
        o = state.order or {}
        name = str(s.get("name"))
        side = str(o.get("side"))
        # rounded for stability
        sl = float(o.get("sl", 0.0))
        tp = float(o.get("tp", 0.0))
        entry = o.get("entry")
        entry_s = "None" if entry is None else f"{float(entry):.2f}"
        return f"{name}|{side}|e={entry_s}|sl={sl:.2f}|tp={tp:.2f}"

    def _coach_note(self, exit_event: Dict[str, Any]) -> Dict[str, Any]:
        r = float(exit_event.get("r", 0.0))
        bars = int(exit_event.get("bars_open", 0))
        tags = []
        if r <= -0.9 and bars <= 3:
            tags.append("stopped_fast")
        if r >= 1.0:
            tags.append("followed_plan_profit")
        return {"tags": tags, "bars_open": bars, "r": r}
