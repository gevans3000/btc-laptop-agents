from __future__ import annotations

from typing import Any, Dict, Optional

from ..indicators import atr, vwap, detect_sweep, ema
from .state import State


class SetupSignalAgent:
    """Agent 3 — Setup/Signal: outputs ONE chosen setup (A/B)."""
    name = "setup_signal"

    def __init__(self, setup_cfg: Dict[str, Any]) -> None:
        self.cfg = setup_cfg

    def run(self, state: State) -> State:
        ctx = state.market_context
        price = float(ctx["price"])
        candles = state.candles
        a = ctx.get("atr") or atr(candles, 14) or (price * 0.004)
        
        # Volatility Filter
        if a / price < 0.0001:
            state.setup = {"name": "NONE", "side": "FLAT", "reason": "low_volatility"}
            return state

        trend = ctx.get("trend", "UNKNOWN")
        ema20 = ctx.get("ema20")
        eq_high = ctx.get("eq_high")
        eq_low = ctx.get("eq_low")

        # Default: no setup
        chosen: Dict[str, Any] = {"name": "NONE", "side": "FLAT", "reason": "no_conditions"}

        # Setup A: Pullback to EMA ribbon (basic scaffold)
        if self.cfg["pullback_ribbon"]["enabled"] and ema20 and trend in ("UP", "DOWN"):
            band = price * float(self.cfg["pullback_ribbon"]["entry_band_pct"])
            entry = float(ema20)
            sl = entry - (a * float(self.cfg["pullback_ribbon"]["stop_atr_mult"])) if trend == "UP" else entry + (a * float(self.cfg["pullback_ribbon"]["stop_atr_mult"]))
            tp = entry + (abs(entry - sl) * float(self.cfg["pullback_ribbon"]["tp_r_mult"])) if trend == "UP" else entry - (abs(entry - sl) * float(self.cfg["pullback_ribbon"]["tp_r_mult"]))

            chosen = {
                "name": "pullback_ribbon",
                "side": "LONG" if trend == "UP" else "SHORT",
                "entry_type": "limit",
                "entry": entry,
                "entry_band": [entry - band, entry + band],
                "sl": sl,
                "tp": tp,
                "conditions_not_to_trade": ["trend_not_clear", "funding_gate_violation"],
            }

        # Setup B: Sweep + VWAP Reclaim (Phase 2 Enhanced)
        if self.cfg["sweep_invalidation"]["enabled"] and chosen["name"] == "NONE":
            tol = price * float(self.cfg["sweep_invalidation"]["eq_tolerance_pct"])
            cvd_div = state.cvd_divergence.get("divergence", "NONE")
            
            # Indicators for Enhancement
            v_vals = vwap(candles)
            cur_vwap = v_vals[-1] if v_vals else price
            cur_ema = ema([c.close for c in candles], int(self.cfg["sweep_invalidation"].get("ema_period", 200)))

            if eq_high:
                # SHORT: Only if below EMA
                ema_ok = (price < cur_ema) if cur_ema and self.cfg["sweep_invalidation"].get("ema_filter") else True
                if ema_ok and cvd_div == "BEARISH":
                    chosen = {
                        "name": "sweep_vwap_reclaim_high",
                        "side": "SHORT",
                        "entry_type": "market_on_trigger",
                        "trigger": {"type": "sweep_and_close_back_below", "level": float(eq_high), "tol": tol},
                        "sl": float(eq_high) + (a * float(self.cfg["sweep_invalidation"].get("stop_atr_mult", 1.0))),
                        "tp": cur_vwap if self.cfg["sweep_invalidation"].get("vwap_target") else float(eq_high) - (a * float(self.cfg["sweep_invalidation"]["tp_r_mult"])),
                        "cvd_conf": True,
                        "conditions_not_to_trade": ["no_sweep_trigger", "funding_gate_violation"],
                    }
                elif not ema_ok:
                    chosen = {"name": "NONE", "side": "FLAT", "reason": "ema_filter_blocked"}
            elif eq_low:
                # LONG: Only if above EMA
                ema_ok = (price > cur_ema) if cur_ema and self.cfg["sweep_invalidation"].get("ema_filter") else True
                if ema_ok and cvd_div == "BULLISH":
                    chosen = {
                        "name": "sweep_vwap_reclaim_low",
                        "side": "LONG",
                        "entry_type": "market_on_trigger",
                        "trigger": {"type": "sweep_and_close_back_above", "level": float(eq_low), "tol": tol},
                        "sl": float(eq_low) - (a * float(self.cfg["sweep_invalidation"].get("stop_atr_mult", 1.0))),
                        "tp": cur_vwap if self.cfg["sweep_invalidation"].get("vwap_target") else float(eq_low) + (a * float(self.cfg["sweep_invalidation"]["tp_r_mult"])),
                        "cvd_conf": True,
                        "conditions_not_to_trade": ["no_sweep_trigger", "funding_gate_violation"],
                    }
                elif not ema_ok:
                    chosen = {"name": "NONE", "side": "FLAT", "reason": "ema_filter_blocked"}

        state.setup = chosen
        return state
