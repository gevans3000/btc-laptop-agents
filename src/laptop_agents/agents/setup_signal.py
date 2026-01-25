"""
SetupSignalAgent: Setup/Signal: outputs ONE chosen setup (A/B).

Part of the Supervisor pipeline. See ENGINEER.md Section 4 for pipeline order.
"""

from __future__ import annotations

from typing import Any, Dict

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

        # Default: no setup
        chosen: Dict[str, Any] = {
            "name": "NONE",
            "side": "FLAT",
            "reason": "no_conditions",
        }

        # Setup A: Pullback to EMA ribbon (basic scaffold)
        if self.cfg["pullback_ribbon"]["enabled"] and ema20 and trend in ("UP", "DOWN"):
            band = price * float(self.cfg["pullback_ribbon"]["entry_band_pct"])
            entry = float(ema20)
            sl = (
                entry - (a * float(self.cfg["pullback_ribbon"]["stop_atr_mult"]))
                if trend == "UP"
                else entry + (a * float(self.cfg["pullback_ribbon"]["stop_atr_mult"]))
            )
            tp = (
                entry
                + (abs(entry - sl) * float(self.cfg["pullback_ribbon"]["tp_r_mult"]))
                if trend == "UP"
                else entry
                - (abs(entry - sl) * float(self.cfg["pullback_ribbon"]["tp_r_mult"]))
            )

            chosen = {
                "name": "pullback_ribbon",
                "side": "LONG" if trend == "UP" else "SHORT",
                "entry_type": "limit",
                "entry": entry,
                "entry_band": [entry - band, entry + band],
                "sl": sl,
                "tp": tp,
                "conditions_not_to_trade": [
                    "trend_not_clear",
                    "funding_gate_violation",
                ],
            }

        # Setup B: Sweep + Reclaim with VWAP target and EMA filter
        if self.cfg["sweep_invalidation"]["enabled"] and chosen["name"] == "NONE":
            sweep = detect_sweep(
                candles,
                lookback=self.cfg["sweep_invalidation"].get("lookback_bars", 10),
            )

            if sweep["reclaimed"]:
                level = sweep["level"]
                session_vwap = vwap(candles[-60:])[-1] if len(candles) >= 1 else price

                # EMA Trend Filter
                e9_vals = [c.close for c in candles]
                ema9 = ema(e9_vals, 9)
                ema20 = ema(e9_vals, 20)
                trend_up = ema9 and ema20 and ema9 > ema20
                trend_down = ema9 and ema20 and ema9 < ema20

                # CVD and Volume
                cvd_div = getattr(state, "cvd_divergence", {}).get("divergence", "NONE")
                req_cvd = self.cfg["sweep_invalidation"].get(
                    "require_cvd_confirm", False
                )
                avg_vol = (
                    sum(c.volume for c in candles[-20:]) / 20
                    if len(candles) >= 20
                    else 0
                )
                curr_vol = candles[-1].volume if candles else 0
                vol_ok = curr_vol >= avg_vol * self.cfg["sweep_invalidation"].get(
                    "min_vol_ratio", 0.5
                )

                if sweep["swept"] == "LOW":
                    if trend_down:
                        chosen["reason"] = "ema_filter_blocked"
                    elif not vol_ok:
                        chosen["reason"] = "volume_filter_blocked"
                    else:
                        cvd_ok = (not req_cvd) or (cvd_div == "BULLISH")
                        if cvd_ok:
                            sl = level - (
                                a
                                * self.cfg["sweep_invalidation"].get(
                                    "stop_atr_mult", 0.5
                                )
                            )
                            tp = session_vwap
                            chosen = {
                                "name": "sweep_reclaim_long",
                                "side": "LONG",
                                "entry_type": "market",
                                "entry": price,
                                "sl": sl,
                                "tp": tp,
                                "swept_level": level,
                                "vwap": session_vwap,
                                "cvd_confirmation": cvd_div == "BULLISH",
                                "conditions_not_to_trade": [
                                    "trend_against",
                                    "funding_gate_violation",
                                ],
                            }
                        else:
                            chosen["reason"] = "cvd_confirmation_failed"

                elif sweep["swept"] == "HIGH":
                    if trend_up:
                        chosen["reason"] = "ema_filter_blocked"
                    elif not vol_ok:
                        chosen["reason"] = "volume_filter_blocked"
                    else:
                        cvd_ok = (not req_cvd) or (cvd_div == "BEARISH")
                        if cvd_ok:
                            sl = level + (
                                a
                                * self.cfg["sweep_invalidation"].get(
                                    "stop_atr_mult", 0.5
                                )
                            )
                            tp = session_vwap
                            chosen = {
                                "name": "sweep_reclaim_short",
                                "side": "SHORT",
                                "entry_type": "market",
                                "entry": price,
                                "sl": sl,
                                "tp": tp,
                                "swept_level": level,
                                "vwap": session_vwap,
                                "cvd_confirmation": cvd_div == "BEARISH",
                                "conditions_not_to_trade": [
                                    "trend_against",
                                    "funding_gate_violation",
                                ],
                            }
                        else:
                            chosen["reason"] = "cvd_confirmation_failed"

        state.setup = chosen
        return state
