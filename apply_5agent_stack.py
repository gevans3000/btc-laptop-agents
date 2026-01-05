from __future__ import annotations

from pathlib import Path
import textwrap

FILES: dict[str, str] = {

# -------------------------
# Trading journal (FIXED)
# -------------------------
"src/laptop_agents/trading/paper_journal.py": r'''
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import json
import uuid
from typing import Any, Dict, Iterable, List, Union


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


PathLike = Union[str, Path]


class PaperJournal:
    """Append-only JSONL paper-trade journal.

    Events:
      - trade:  {"type":"trade", ...}
      - update: {"type":"update", ...}
    """

    def __init__(self, path: PathLike = "data/paper_journal.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def new_trade(
        self,
        *,
        instrument: str,
        timeframe: str,
        direction: str,
        plan: Dict[str, Any],
        trade_id: str | None = None,
    ) -> str:
        tid = trade_id or f"PT-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        event = {
            "type": "trade",
            "trade_id": tid,
            "created_at": _now_iso(),
            "instrument": instrument,
            "timeframe": timeframe,
            "direction": direction,
            "plan": plan,
        }
        self._append(event)
        return tid

    def add_update(self, trade_id: str, update: Dict[str, Any]) -> None:
        event = {"type": "update", "trade_id": trade_id, "at": _now_iso(), **update}
        self._append(event)

    def iter_events(self) -> Iterable[Dict[str, Any]]:
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def last(self, n: int = 5) -> List[Dict[str, Any]]:
        events = list(self.iter_events())
        return events[-n:]

    def _append(self, obj: Dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
''',

"src/laptop_agents/trading/__init__.py": r'''
from .paper_journal import PaperJournal

__all__ = ["PaperJournal"]
''',

# -------------------------
# Config (extend later)
# -------------------------
"config/default.json": r'''
{
  "instrument": "BTCUSDT",
  "timeframe": "5m",

  "risk": {
    "equity": 10000.0,
    "risk_pct": 0.01,
    "rr_min": 1.8
  },

  "derivatives_gates": {
    "half_size_funding_8h": 0.0003,
    "no_trade_funding_8h": 0.0010
  },

  "setups": {
    "pullback_ribbon": {
      "enabled": true,
      "ema_fast": 20,
      "ema_slow": 50,
      "entry_band_pct": 0.0015,
      "stop_atr_mult": 1.2,
      "tp_r_mult": 1.8
    },
    "sweep_invalidation": {
      "enabled": true,
      "eq_tolerance_pct": 0.0008,
      "lookback": 40,
      "tp_r_mult": 2.0
    }
  }
}
''',

# -------------------------
# Data Providers
# -------------------------
"src/laptop_agents/data/providers/__init__.py": r'''
from .mock import MockProvider
from .binance_futures import BinanceFuturesProvider

__all__ = ["MockProvider", "BinanceFuturesProvider"]
''',

"src/laptop_agents/data/providers/mock.py": r'''
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List
import random


@dataclass(frozen=True)
class Candle:
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class MockProvider:
    """Deterministic candle stream for tests/demos (no internet)."""

    def __init__(self, seed: int = 7, start: float = 100_000.0) -> None:
        self.rng = random.Random(seed)
        self.price = start
        self.now = datetime.now(timezone.utc) - timedelta(minutes=5 * 500)

    def next_candle(self) -> Candle:
        self.now = self.now + timedelta(minutes=5)

        # Create a mild trend + noise so setups actually trigger
        drift = 0.00015
        noise = self.rng.uniform(-0.0009, 0.0009)
        self.price = max(1000.0, self.price * (1.0 + drift + noise))

        o = self.price * (1.0 - self.rng.uniform(0.0002, 0.0006))
        c = self.price
        hi = max(o, c) * (1.0 + self.rng.uniform(0.0002, 0.0007))
        lo = min(o, c) * (1.0 - self.rng.uniform(0.0002, 0.0007))
        v = 1.0

        return Candle(ts=self.now.isoformat(), open=o, high=hi, low=lo, close=c, volume=v)

    def history(self, n: int = 200) -> List[Candle]:
        return [self.next_candle() for _ in range(n)]
''',

"src/laptop_agents/data/providers/binance_futures.py": r'''
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict, Any


@dataclass(frozen=True)
class Candle:
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class BinanceFuturesProvider:
    """Public endpoints for USDT-margined Binance Futures.
    NOTE: requires `pip install httpx` only if you use this provider.
    """

    BASE = "https://fapi.binance.com"

    def __init__(self, symbol: str = "BTCUSDT") -> None:
        self.symbol = symbol

    def klines(self, interval: str = "5m", limit: int = 500) -> List[Candle]:
        import httpx  # lazy import

        url = f"{self.BASE}/fapi/v1/klines"
        params = {"symbol": self.symbol, "interval": interval, "limit": limit}
        with httpx.Client(timeout=20) as c:
            r = c.get(url, params=params)
            r.raise_for_status()
            data = r.json()

        out: List[Candle] = []
        for k in data:
            # kline open time is ms
            ts = int(k[0])
            out.append(
                Candle(
                    ts=str(ts),
                    open=float(k[1]),
                    high=float(k[2]),
                    low=float(k[3]),
                    close=float(k[4]),
                    volume=float(k[5]),
                )
            )
        return out

    def funding_8h(self) -> Optional[float]:
        import httpx  # lazy import

        # premiumIndex includes lastFundingRate
        url = f"{self.BASE}/fapi/v1/premiumIndex"
        params = {"symbol": self.symbol}
        with httpx.Client(timeout=20) as c:
            r = c.get(url, params=params)
            r.raise_for_status()
            j = r.json()
        try:
            return float(j.get("lastFundingRate"))
        except Exception:
            return None

    def open_interest(self) -> Optional[float]:
        import httpx  # lazy import

        url = f"{self.BASE}/fapi/v1/openInterest"
        params = {"symbol": self.symbol}
        with httpx.Client(timeout=20) as c:
            r = c.get(url, params=params)
            r.raise_for_status()
            j = r.json()
        try:
            return float(j.get("openInterest"))
        except Exception:
            return None

    def snapshot_derivatives(self) -> Dict[str, Any]:
        return {
            "funding_8h": self.funding_8h(),
            "open_interest": self.open_interest(),
            "basis": None,
            "liq_map": None
        }
''',

# -------------------------
# Indicators / Utilities
# -------------------------
"src/laptop_agents/indicators.py": r'''
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple
import math


@dataclass(frozen=True)
class Candle:
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float


def ema(values: List[float], period: int) -> Optional[float]:
    if period <= 0 or len(values) < period:
        return None
    k = 2 / (period + 1)
    e = sum(values[:period]) / period
    for v in values[period:]:
        e = (v * k) + (e * (1 - k))
    return e


def true_range(prev_close: float, high: float, low: float) -> float:
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def atr(candles: List[Candle], period: int = 14) -> Optional[float]:
    if len(candles) < period + 1:
        return None
    trs: List[float] = []
    for i in range(1, len(candles)):
        trs.append(true_range(candles[i-1].close, candles[i].high, candles[i].low))
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


def swing_high_low(candles: List[Candle], lookback: int = 40) -> Tuple[Optional[float], Optional[float]]:
    if not candles:
        return None, None
    window = candles[-lookback:] if len(candles) >= lookback else candles
    hi = max(c.high for c in window)
    lo = min(c.low for c in window)
    return hi, lo


def equal_level(values: List[float], tol_pct: float = 0.0008) -> Optional[float]:
    """Return a level if at least 2 recent values cluster within tolerance."""
    if len(values) < 6:
        return None
    recent = values[-12:]
    # compare last value to earlier values in recent window
    last = recent[-1]
    tol = abs(last) * tol_pct
    matches = [v for v in recent[:-1] if abs(v - last) <= tol]
    if len(matches) >= 1:
        # average cluster
        return (sum(matches) + last) / (len(matches) + 1)
    return None
''',

# -------------------------
# Paper Broker
# -------------------------
"src/laptop_agents/paper/__init__.py": r'''
from .broker import PaperBroker

__all__ = ["PaperBroker"]
''',

"src/laptop_agents/paper/broker.py": r'''
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass
class Position:
    side: str  # LONG / SHORT
    entry: float
    qty: float
    sl: float
    tp: float
    opened_at: str
    bars_open: int = 0


class PaperBroker:
    """Very simple broker:
    - one position max
    - one TP + one SL
    - conservative intrabar resolution (stop-first if both touched)
    """

    def __init__(self) -> None:
        self.pos: Optional[Position] = None

    def on_candle(self, candle: Any, order: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        events: Dict[str, Any] = {"fills": [], "exits": []}

        # 1) manage open position
        if self.pos is not None:
            self.pos.bars_open += 1
            exit_event = self._check_exit(candle)
            if exit_event:
                events["exits"].append(exit_event)
                self.pos = None

        # 2) open new position if none
        if self.pos is None and order and order.get("go"):
            fill = self._try_fill(candle, order)
            if fill:
                events["fills"].append(fill)

        return events

    def _try_fill(self, candle: Any, order: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        entry_type = order["entry_type"]  # "limit" or "market"
        entry = float(order["entry"])
        side = order["side"]
        qty = float(order["qty"])
        sl = float(order["sl"])
        tp = float(order["tp"])

        if entry_type == "market":
            fill_px = float(candle.close)
        else:
            # limit fill if touched
            if not (candle.low <= entry <= candle.high):
                return None
            fill_px = entry

        self.pos = Position(side=side, entry=fill_px, qty=qty, sl=sl, tp=tp, opened_at=candle.ts)
        return {"type": "fill", "side": side, "price": fill_px, "qty": qty, "sl": sl, "tp": tp, "at": candle.ts}

    def _check_exit(self, candle: Any) -> Optional[Dict[str, Any]]:
        assert self.pos is not None
        p = self.pos

        if p.side == "LONG":
            sl_hit = candle.low <= p.sl
            tp_hit = candle.high >= p.tp
            if sl_hit and tp_hit:
                # conservative: assume stop first
                return self._exit(candle.ts, p.sl, "SL_conservative")
            if sl_hit:
                return self._exit(candle.ts, p.sl, "SL")
            if tp_hit:
                return self._exit(candle.ts, p.tp, "TP")
        else:  # SHORT
            sl_hit = candle.high >= p.sl
            tp_hit = candle.low <= p.tp
            if sl_hit and tp_hit:
                return self._exit(candle.ts, p.sl, "SL_conservative")
            if sl_hit:
                return self._exit(candle.ts, p.sl, "SL")
            if tp_hit:
                return self._exit(candle.ts, p.tp, "TP")

        return None

    def _exit(self, ts: str, px: float, reason: str) -> Dict[str, Any]:
        assert self.pos is not None
        p = self.pos
        pnl = (px - p.entry) * p.qty if p.side == "LONG" else (p.entry - px) * p.qty
        risk = abs(p.entry - p.sl) * p.qty
        r_mult = (pnl / risk) if risk > 0 else 0.0
        return {"type": "exit", "reason": reason, "price": px, "pnl": pnl, "r": r_mult, "bars_open": p.bars_open, "at": ts}
''',

# -------------------------
# 5 Agents + Supervisor
# -------------------------
"src/laptop_agents/agents/state.py": r'''
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..indicators import Candle


@dataclass
class State:
    instrument: str = "BTCUSDT"
    timeframe: str = "5m"

    candles: List[Candle] = field(default_factory=list)

    market_context: Dict[str, Any] = field(default_factory=dict)
    derivatives: Dict[str, Any] = field(default_factory=dict)

    setup: Dict[str, Any] = field(default_factory=dict)        # chosen setup
    order: Dict[str, Any] = field(default_factory=dict)        # validated order plan

    broker_events: Dict[str, Any] = field(default_factory=dict)

    trade_id: Optional[str] = None
''',

"src/laptop_agents/agents/market_intake.py": r'''
from __future__ import annotations

from typing import Any, Dict, List

from ..indicators import Candle, ema, atr, swing_high_low, equal_level
from .state import State


class MarketIntakeAgent:
    """Agent 1 — Market Intake: structure, levels, regime, what changed."""
    name = "market_intake"

    def run(self, state: State) -> State:
        candles = state.candles
        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        last = closes[-1]

        ema_fast = ema(closes, 20)
        ema_slow = ema(closes, 50)

        trend = "UNKNOWN"
        if ema_fast and ema_slow:
            if ema_fast > ema_slow and last > ema_fast:
                trend = "UP"
            elif ema_fast < ema_slow and last < ema_fast:
                trend = "DOWN"
            else:
                trend = "CHOP"

        a = atr(candles, 14)
        atr_pct = (a / last) if a else None
        if atr_pct is None:
            regime = "UNKNOWN"
        elif atr_pct < 0.002:
            regime = "CHOP_LOWVOL"
        elif atr_pct > 0.006:
            regime = "TREND_HIGHVOL"
        else:
            regime = "NORMAL"

        swing_hi, swing_lo = swing_high_low(candles, lookback=40)
        eq_high = equal_level(highs, tol_pct=0.0008)
        eq_low = equal_level(lows, tol_pct=0.0008)

        bullets: List[str] = []
        bullets.append(f"Trend={trend} Regime={regime}")
        if swing_hi and swing_lo:
            bullets.append(f"Swing range: {swing_lo:,.0f} → {swing_hi:,.0f}")
        if eq_high:
            bullets.append(f"Equal-highs zone ~{eq_high:,.0f}")
        if eq_low:
            bullets.append(f"Equal-lows zone ~{eq_low:,.0f}")

        state.market_context = {
            "price": last,
            "trend": trend,
            "regime": regime,
            "ema20": ema_fast,
            "ema50": ema_slow,
            "swing_high": swing_hi,
            "swing_low": swing_lo,
            "eq_high": eq_high,
            "eq_low": eq_low,
            "bullets": bullets[-5:],
            "atr": a,
            "atr_pct": atr_pct,
        }
        return state
''',

"src/laptop_agents/agents/derivatives_flows.py": r'''
from __future__ import annotations

from typing import Any, Dict, Optional

from .state import State


class DerivativesFlowsAgent:
    """Agent 2 — Derivatives/Flows: funding/OI (basis/liq-map scaffold)."""
    name = "derivatives_flows"

    def __init__(self, provider: Any, gates: Dict[str, float]) -> None:
        self.provider = provider
        self.gates = gates

    def run(self, state: State) -> State:
        snap: Dict[str, Any] = {"funding_8h": None, "open_interest": None, "basis": None, "liq_map": None}
        if hasattr(self.provider, "snapshot_derivatives"):
            try:
                snap = self.provider.snapshot_derivatives()
            except Exception:
                snap["error"] = "snapshot_failed"

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
''',

"src/laptop_agents/agents/setup_signal.py": r'''
from __future__ import annotations

from typing import Any, Dict, Optional

from ..indicators import atr
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

        # Setup B: Sweep + invalidation (scaffold)
        # NOTE: full sweep logic evolves later; here we flag a watch setup if eq zones exist.
        if self.cfg["sweep_invalidation"]["enabled"]:
            tol = price * float(self.cfg["sweep_invalidation"]["eq_tolerance_pct"])
            if eq_high:
                chosen = {
                    "name": "sweep_invalidation_eq_high",
                    "side": "SHORT",
                    "entry_type": "market_on_trigger",
                    "trigger": {"type": "sweep_and_close_back_below", "level": float(eq_high), "tol": tol},
                    "sl": float(eq_high) + (a * 0.8),
                    "tp": float(eq_high) - (a * float(self.cfg["sweep_invalidation"]["tp_r_mult"])),
                    "conditions_not_to_trade": ["no_sweep_trigger", "funding_gate_violation"],
                }
            elif eq_low:
                chosen = {
                    "name": "sweep_invalidation_eq_low",
                    "side": "LONG",
                    "entry_type": "market_on_trigger",
                    "trigger": {"type": "sweep_and_close_back_above", "level": float(eq_low), "tol": tol},
                    "sl": float(eq_low) - (a * 0.8),
                    "tp": float(eq_low) + (a * float(self.cfg["sweep_invalidation"]["tp_r_mult"])),
                    "conditions_not_to_trade": ["no_sweep_trigger", "funding_gate_violation"],
                }

        state.setup = chosen
        return state
''',

"src/laptop_agents/agents/execution_risk.py": r'''
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

        # Funding gates
        size_mult = 1.0
        if "NO_TRADE_funding_hot" in flags:
            state.order = {"go": False, "reason": "funding_hot_no_trade", "setup": setup}
            return state
        if "HALF_SIZE_funding_warm" in flags:
            size_mult = 0.5

        # Entry resolution
        side = setup["side"]

        entry_type = setup.get("entry_type")
        entry: Optional[float] = None

        if entry_type == "limit":
            entry = float(setup["entry"])
        elif entry_type == "market_on_trigger":
            # resolved in supervisor when trigger fires
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
''',

"src/laptop_agents/agents/journal_coach.py": r'''
from __future__ import annotations

from typing import Any, Dict, Optional

from ..trading import PaperJournal
from .state import State


class JournalCoachAgent:
    """Agent 5 — Journal & Coach: log plan + fills + exits, extract rule notes."""
    name = "journal_coach"

    def __init__(self, journal_path: str = "data/paper_journal.jsonl") -> None:
        self.j = PaperJournal(journal_path)

    def run(self, state: State) -> State:
        # Create trade record once we have an order that is actionable (or pending trigger)
        if state.trade_id is None and state.order.get("go"):
            plan = {
                "market_context": state.market_context,
                "derivatives": state.derivatives,
                "setup": state.setup,
                "order": state.order,
            }
            state.trade_id = self.j.new_trade(
                instrument=state.instrument,
                timeframe=state.timeframe,
                direction=state.order.get("side", "FLAT"),
                plan=plan,
            )
            self.j.add_update(state.trade_id, {"note": "plan_created"})

        # Log broker events (fills/exits)
        if state.trade_id and state.broker_events:
            for f in state.broker_events.get("fills", []):
                self.j.add_update(state.trade_id, {"note": "fill", "fill": f})
            for x in state.broker_events.get("exits", []):
                coach_note = self._coach_note(x)
                self.j.add_update(state.trade_id, {"note": "exit", "exit": x, "coach": coach_note})

        return state

    def _coach_note(self, exit_event: Dict[str, Any]) -> Dict[str, Any]:
        r = float(exit_event.get("r", 0.0))
        bars = int(exit_event.get("bars_open", 0))
        tags = []
        if r <= -0.9 and bars <= 3:
            tags.append("stopped_fast")
        if r >= 1.0:
            tags.append("followed_plan_profit")
        return {"tags": tags, "bars_open": bars, "r": r}
''',

"src/laptop_agents/agents/supervisor.py": r'''
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..indicators import Candle
from ..paper import PaperBroker
from .state import State
from .market_intake import MarketIntakeAgent
from .derivatives_flows import DerivativesFlowsAgent
from .setup_signal import SetupSignalAgent
from .execution_risk import ExecutionRiskSentinelAgent
from .journal_coach import JournalCoachAgent


class Supervisor:
    def __init__(self, provider: Any, cfg: Dict[str, Any], journal_path: str = "data/paper_journal.jsonl") -> None:
        self.provider = provider
        self.cfg = cfg
        self.broker = PaperBroker()

        self.a1 = MarketIntakeAgent()
        self.a2 = DerivativesFlowsAgent(provider, cfg["derivatives_gates"])
        self.a3 = SetupSignalAgent(cfg["setups"])
        self.a4 = ExecutionRiskSentinelAgent(cfg["risk"])
        self.a5 = JournalCoachAgent(journal_path)

        self.agents = [self.a1, self.a2, self.a3, self.a4, self.a5]

    def step(self, state: State, candle: Candle) -> State:
        state.candles.append(candle)
        state.candles = state.candles[-800:]

        # Run A1..A4 to produce an order (or pending trigger)
        state = self.a1.run(state)
        state = self.a2.run(state)
        state = self.a3.run(state)
        state = self.a4.run(state)

        # Resolve trigger -> market entry if needed
        order = self._resolve_order(state, candle)

        # Broker handles fills/exits
        state.broker_events = self.broker.on_candle(candle, order)

        # Journal/Coach logs everything
        state = self.a5.run(state)
        return state

    def _resolve_order(self, state: State, candle: Candle) -> Optional[Dict[str, Any]]:
        order = dict(state.order or {})
        if not order.get("go"):
            return None

        setup = order.get("setup", {})
        risk_dollars = float(order["equity"]) * float(order["risk_pct"]) * float(order["size_mult"])

        # Market-on-trigger sweep logic (scaffold)
        if setup.get("entry_type") == "market_on_trigger":
            trig = setup.get("trigger", {})
            if trig.get("type") == "sweep_and_close_back_below":
                lvl = float(trig["level"]); tol = float(trig["tol"])
                if candle.high > (lvl + tol) and candle.close < lvl:
                    entry = float(candle.close)
                else:
                    return None
            elif trig.get("type") == "sweep_and_close_back_above":
                lvl = float(trig["level"]); tol = float(trig["tol"])
                if candle.low < (lvl - tol) and candle.close > lvl:
                    entry = float(candle.close)
                else:
                    return None
            else:
                return None
            order["entry_type"] = "market"
            order["entry"] = entry

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
''',

"src/laptop_agents/agents/__init__.py": r'''
from .state import State
from .supervisor import Supervisor

__all__ = ["State", "Supervisor"]
''',

# -------------------------
# CLI
# -------------------------
"src/laptop_agents/cli.py": r'''
from __future__ import annotations

import json
from pathlib import Path
import typer
from rich import print

from .agents import State, Supervisor
from .data.providers import MockProvider, BinanceFuturesProvider
from .indicators import Candle


app = typer.Typer(help="BTC Laptop Agents — 5-agent paper trading loop (5m)")


def load_cfg(path: str = "config/default.json") -> dict:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


@app.command()
def agents():
    """List the 5 agents."""
    print("- market_intake")
    print("- derivatives_flows")
    print("- setup_signal")
    print("- execution_risk_sentinel")
    print("- journal_coach")


@app.command()
def run_mock(steps: int = 200, seed: int = 7, cfg: str = "config/default.json", journal: str = "data/paper_journal.jsonl"):
    """Run paper loop on mock candles (no internet)."""
    c = load_cfg(cfg)
    provider = MockProvider(seed=seed, start=100_000.0)
    sup = Supervisor(provider=provider, cfg=c, journal_path=journal)

    state = State(instrument=c["instrument"], timeframe=c["timeframe"])
    candles = provider.history(steps)

    for i, mc in enumerate(candles, start=1):
        candle = Candle(ts=mc.ts, open=mc.open, high=mc.high, low=mc.low, close=mc.close, volume=mc.volume)
        state = sup.step(state, candle)
        if i % 25 == 0:
            px = state.market_context.get("price")
            print(f"[{i}/{steps}] price={px:,.0f} setup={state.setup.get('name')} trade_id={state.trade_id}")

    print(f"[green]Done[/green]. Journal: {journal}")


@app.command()
def run_live_history(limit: int = 500, cfg: str = "config/default.json", journal: str = "data/paper_journal.jsonl"):
    """Run over the last N Binance Futures 5m klines (requires: pip install httpx)."""
    c = load_cfg(cfg)
    provider = BinanceFuturesProvider(symbol=c["instrument"])
    sup = Supervisor(provider=provider, cfg=c, journal_path=journal)

    state = State(instrument=c["instrument"], timeframe=c["timeframe"])
    kl = provider.klines(interval=c["timeframe"], limit=limit)

    for i, k in enumerate(kl, start=1):
        candle = Candle(ts=k.ts, open=k.open, high=k.high, low=k.low, close=k.close, volume=k.volume)
        state = sup.step(state, candle)
        if i % 50 == 0:
            px = state.market_context.get("price")
            print(f"[{i}/{limit}] price={px:,.0f} setup={state.setup.get('name')} trade_id={state.trade_id}")

    print(f"[green]Done[/green]. Journal: {journal}")


@app.command()
def journal_tail(n: int = 10, journal: str = "data/paper_journal.jsonl"):
    """Print last N journal events."""
    from .trading import PaperJournal
    j = PaperJournal(journal)
    for e in j.last(n):
        print(e)


if __name__ == "__main__":
    app()
''',

# -------------------------
# Dev helper
# -------------------------
"tools/dev.ps1": r'''
param(
  [Parameter(Position=0)][string]$cmd="help"
)

if ($cmd -eq "install") {
  python -m pip install -e .
  exit 0
}

if ($cmd -eq "test") {
  pytest -q
  exit 0
}

if ($cmd -eq "demo") {
  python -m laptop_agents.cli run-mock --steps 250
  python -m laptop_agents.cli journal-tail --n 12
  exit 0
}

if ($cmd -eq "live") {
  python -m pip install httpx
  python -m laptop_agents.cli run-live-history --limit 500
  exit 0
}

Write-Host "Usage:"
Write-Host "  .\tools\dev.ps1 install"
Write-Host "  .\tools\dev.ps1 test"
Write-Host "  .\tools\dev.ps1 demo"
Write-Host "  .\tools\dev.ps1 live"
''',

# -------------------------
# Tests
# -------------------------
"tests/test_pipeline_smoke.py": r'''
from pathlib import Path
from laptop_agents.data.providers import MockProvider
from laptop_agents.agents import State, Supervisor
from laptop_agents.indicators import Candle
import json


def test_pipeline_smoke(tmp_path):
    cfg = json.loads(Path("config/default.json").read_text(encoding="utf-8"))
    journal = tmp_path / "paper_journal.jsonl"

    provider = MockProvider(seed=7, start=100_000.0)
    sup = Supervisor(provider=provider, cfg=cfg, journal_path=str(journal))

    state = State(instrument=cfg["instrument"], timeframe=cfg["timeframe"])

    for mc in provider.history(120):
        c = Candle(ts=mc.ts, open=mc.open, high=mc.high, low=mc.low, close=mc.close, volume=mc.volume)
        state = sup.step(state, c)

    assert journal.exists()
    content = journal.read_text(encoding="utf-8").strip().splitlines()
    assert len(content) > 0
''',

"tests/test_paper_journal.py": r'''
from laptop_agents.trading.paper_journal import PaperJournal


def test_paper_journal_roundtrip(tmp_path):
    p = tmp_path / "paper_journal.jsonl"
    j = PaperJournal(p)

    tid = j.new_trade(
        instrument="BTCUSDT",
        timeframe="5m",
        direction="LONG",
        plan={"entry": 112000, "sl": 111500, "tps": [112500, 113000]},
    )
    j.add_update(tid, {"note": "TP1 hit", "realized_r": 1.0})

    events = list(j.iter_events())
    assert events[0]["type"] == "trade"
    assert events[0]["trade_id"] == tid
    assert events[1]["type"] == "update"
    assert events[1]["trade_id"] == tid
''',
}


def _write(path: str, content: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    normalized = textwrap.dedent(content).lstrip("\n").rstrip() + "\n"
    p.write_text(normalized, encoding="utf-8")


def main() -> None:
    for path, content in FILES.items():
        _write(path, content)
    print("Revamp applied: 5-agent stack + paper broker + CLI + tests.")


if __name__ == "__main__":
    main()
