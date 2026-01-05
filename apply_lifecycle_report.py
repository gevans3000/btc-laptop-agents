from __future__ import annotations

from pathlib import Path
import textwrap

FILES: dict[str, str] = {

# -------------------------
# Config: add engine knobs
# -------------------------
"config/default.json": r'''
{
  "instrument": "BTCUSDT",
  "timeframe": "5m",

  "engine": {
    "pending_trigger_max_bars": 24,
    "derivatives_refresh_bars": 6
  },

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
# State: add meta + pending bars
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

    setup: Dict[str, Any] = field(default_factory=dict)
    order: Dict[str, Any] = field(default_factory=dict)

    broker_events: Dict[str, Any] = field(default_factory=dict)

    trade_id: Optional[str] = None

    # lifecycle helpers
    pending_trigger_bars: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)
''',

# -------------------------
# Derivatives agent: cache snapshot
# -------------------------
"src/laptop_agents/agents/derivatives_flows.py": r'''
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
''',

# -------------------------
# Journal coach: dedupe plans + reset after exit/cancel
# -------------------------
"src/laptop_agents/agents/journal_coach.py": r'''
from __future__ import annotations

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
                state.trade_id = self.j.new_trade(
                    instrument=state.instrument,
                    timeframe=state.timeframe,
                    direction=state.order.get("side", "FLAT"),
                    plan=plan,
                )
                self.j.add_update(state.trade_id, {"note": "plan_created", "plan_key": plan_key})

        # Log cancels (then reset to allow new plans)
        if state.trade_id and cancels:
            for c in cancels:
                self.j.add_update(state.trade_id, {"note": "canceled", "cancel": c})
            state.trade_id = None
            state.pending_trigger_bars = 0
            return state

        # Log fills/exits
        if state.trade_id:
            for f in fills:
                self.j.add_update(state.trade_id, {"note": "fill", "fill": f})
            for x in exits:
                coach_note = self._coach_note(x)
                self.j.add_update(state.trade_id, {"note": "exit", "exit": x, "coach": coach_note})
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
''',

# -------------------------
# Supervisor: pending-trigger expiry -> cancel event
# -------------------------
"src/laptop_agents/agents/supervisor.py": r'''
from __future__ import annotations

from typing import Any, Dict, Optional

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

        engine = cfg.get("engine", {})
        self.pending_trigger_max_bars = int(engine.get("pending_trigger_max_bars", 24))
        refresh_bars = int(engine.get("derivatives_refresh_bars", 6))

        self.a1 = MarketIntakeAgent()
        self.a2 = DerivativesFlowsAgent(provider, cfg["derivatives_gates"], refresh_bars=refresh_bars)
        self.a3 = SetupSignalAgent(cfg["setups"])
        self.a4 = ExecutionRiskSentinelAgent(cfg["risk"])
        self.a5 = JournalCoachAgent(journal_path)

    def step(self, state: State, candle: Candle) -> State:
        state.candles.append(candle)
        state.candles = state.candles[-800:]

        # A1..A4 produce an order (or pending trigger)
        state = self.a1.run(state)
        state = self.a2.run(state)
        state = self.a3.run(state)
        state = self.a4.run(state)

        # pending-trigger lifecycle (time stop)
        cancels = []
        if state.order.get("go") and state.order.get("pending_trigger"):
            state.pending_trigger_bars += 1
            if state.pending_trigger_bars >= self.pending_trigger_max_bars:
                cancels.append({"reason": "pending_trigger_expired", "bars": state.pending_trigger_bars, "at": candle.ts})
                # stop trying until next setup changes (journal agent will reset trade_id)
                state.order = {"go": False, "reason": "pending_trigger_expired"}
        else:
            state.pending_trigger_bars = 0

        # Resolve trigger -> market entry if needed
        order = self._resolve_order(state, candle)

        # Broker handles fills/exits
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

# -------------------------
# Reporting module + CLI command
# -------------------------
"src/laptop_agents/reporting.py": r'''
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import csv
import json
from datetime import datetime


@dataclass
class TradeRow:
    trade_id: str
    created_at: str
    setup: str
    direction: str
    entry: Optional[float]
    exit_price: Optional[float]
    r: Optional[float]
    pnl: Optional[float]
    bars_open: Optional[int]
    reason: str


def load_events(journal_path: str) -> List[Dict[str, Any]]:
    p = Path(journal_path)
    if not p.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def summarize(journal_path: str) -> Tuple[Dict[str, Any], List[TradeRow]]:
    events = load_events(journal_path)
    trades: Dict[str, Dict[str, Any]] = {}

    for e in events:
        t = e.get("type")
        tid = e.get("trade_id")
        if not tid:
            continue

        if t == "trade":
            plan = e.get("plan") or {}
            setup = (((plan.get("setup") or {}).get("name")) or "UNKNOWN")
            trades[tid] = {
                "trade": e,
                "setup": setup,
                "fills": [],
                "exits": [],
                "cancels": [],
            }
        elif t == "update" and tid in trades:
            note = e.get("note")
            if note == "fill":
                trades[tid]["fills"].append(e.get("fill") or {})
            elif note == "exit":
                trades[tid]["exits"].append(e.get("exit") or {})
            elif note == "canceled":
                trades[tid]["cancels"].append(e.get("cancel") or {})

    rows: List[TradeRow] = []
    r_list: List[float] = []
    setup_counts: Dict[str, int] = {}
    setup_r: Dict[str, List[float]] = {}

    for tid, obj in trades.items():
        trade = obj["trade"]
        created_at = trade.get("created_at", "")
        direction = trade.get("direction", "")
        setup = obj.get("setup", "UNKNOWN")

        setup_counts[setup] = setup_counts.get(setup, 0) + 1

        fill = obj["fills"][-1] if obj["fills"] else None
        exit_ev = obj["exits"][-1] if obj["exits"] else None
        cancel_ev = obj["cancels"][-1] if obj["cancels"] else None

        entry = float(fill["price"]) if fill and "price" in fill else None
        exit_price = float(exit_ev["price"]) if exit_ev and "price" in exit_ev else None
        r = float(exit_ev["r"]) if exit_ev and "r" in exit_ev else None
        pnl = float(exit_ev["pnl"]) if exit_ev and "pnl" in exit_ev else None
        bars = int(exit_ev["bars_open"]) if exit_ev and "bars_open" in exit_ev else None

        reason = "OPEN_OR_PLANNED"
        if exit_ev:
            reason = str(exit_ev.get("reason", "EXIT"))
        elif cancel_ev:
            reason = f"CANCELED:{cancel_ev.get('reason')}"

        if r is not None:
            r_list.append(r)
            setup_r.setdefault(setup, []).append(r)

        rows.append(
            TradeRow(
                trade_id=tid,
                created_at=created_at,
                setup=setup,
                direction=direction,
                entry=entry,
                exit_price=exit_price,
                r=r,
                pnl=pnl,
                bars_open=bars,
                reason=reason,
            )
        )

    # Metrics (only closed trades with r)
    closed = [x for x in rows if x.r is not None]
    wins = [x for x in closed if (x.r or 0) > 0]
    losses = [x for x in closed if (x.r or 0) <= 0]

    total_r = sum((x.r or 0) for x in closed)
    avg_r = (total_r / len(closed)) if closed else 0.0
    winrate = (len(wins) / len(closed)) if closed else 0.0
    pf = (sum((x.r or 0) for x in wins) / abs(sum((x.r or 0) for x in losses))) if losses else float("inf")

    # Max drawdown on cumulative R
    peak = 0.0
    eq = 0.0
    max_dd = 0.0
    for x in closed:
        eq += (x.r or 0)
        peak = max(peak, eq)
        max_dd = min(max_dd, eq - peak)  # negative number

    summary = {
        "journal": journal_path,
        "planned_trades": len(rows),
        "closed_trades": len(closed),
        "winrate": winrate,
        "avg_r": avg_r,
        "total_r": total_r,
        "profit_factor_r": pf,
        "max_drawdown_r": max_dd,
        "setups": {k: {"planned": setup_counts.get(k, 0), "avg_r": (sum(v)/len(v) if v else None), "n_closed": len(v)} for k, v in setup_r.items()},
    }
    return summary, rows


def write_report(journal_path: str, out_dir: str = "data/reports") -> Dict[str, str]:
    outp = Path(out_dir)
    outp.mkdir(parents=True, exist_ok=True)

    summary, rows = summarize(journal_path)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    md_path = outp / f"report_{ts}.md"
    csv_path = outp / f"trades_{ts}.csv"

    # markdown
    lines: List[str] = []
    lines.append(f"# BTC Laptop Agents Report ({ts})")
    lines.append("")
    lines.append(f"- Journal: `{journal_path}`")
    lines.append(f"- Planned trades: {summary['planned_trades']}")
    lines.append(f"- Closed trades: {summary['closed_trades']}")
    lines.append(f"- Winrate: {summary['winrate']:.2%}")
    lines.append(f"- Avg R: {summary['avg_r']:.3f}")
    lines.append(f"- Total R: {summary['total_r']:.3f}")
    lines.append(f"- Profit factor (R): {summary['profit_factor_r']:.3f}" if summary["profit_factor_r"] != float("inf") else "- Profit factor (R): inf")
    lines.append(f"- Max drawdown (R): {summary['max_drawdown_r']:.3f}")
    lines.append("")
    lines.append("## Setup breakdown")
    if summary["setups"]:
        for k, v in summary["setups"].items():
            lines.append(f"- **{k}**: planned={v['planned']} closed={v['n_closed']} avg_r={(v['avg_r'] if v['avg_r'] is not None else 'n/a')}")
    else:
        lines.append("- (no closed trades yet)")
    lines.append("")
    lines.append("## Notes")
    lines.append("- Closed trades are those with an `exit` event (R realized).")
    lines.append("- Planned-only trades (no fill/exit) are excluded from winrate/avgR.")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # csv
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["trade_id", "created_at", "setup", "direction", "entry", "exit_price", "r", "pnl", "bars_open", "reason"])
        for r in rows:
            w.writerow([r.trade_id, r.created_at, r.setup, r.direction, r.entry, r.exit_price, r.r, r.pnl, r.bars_open, r.reason])

    return {"md": str(md_path), "csv": str(csv_path)}
''',

# Add CLI command: report
"src/laptop_agents/cli.py": r'''
from __future__ import annotations

import json
from pathlib import Path
import typer
from rich import print

from .agents import State, Supervisor
from .data.providers import (
    MockProvider,
    BinanceFuturesProvider,
    KrakenSpotProvider,
    BybitDerivativesProvider,
    OkxSwapProvider,
    CompositeProvider,
)
from .indicators import Candle

app = typer.Typer(help="BTC Laptop Agents — 5-agent paper trading loop (5m)")


def load_cfg(path: str = "config/default.json") -> dict:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


@app.command()
def debug_feeds(cfg: str = "config/default.json"):
    c = load_cfg(cfg)
    sym = c["instrument"]
    tf = c["timeframe"]

    print("[bold]Binance Futures candles[/bold]")
    try:
        b = BinanceFuturesProvider(symbol=sym)
        kl = b.klines(interval=tf, limit=5)
        print(f"[green]OK[/green] last_close={kl[-1].close}")
    except Exception as e:
        print(f"[yellow]FAIL[/yellow] {e}")

    print("\n[bold]OKX swap candles + derivatives[/bold]")
    try:
        o = OkxSwapProvider(instrument=sym)
        kl = o.klines(interval=tf, limit=5)
        d = o.snapshot_derivatives()
        print(f"[green]OK[/green] instId={d.get('inst_id', 'BTC-USDT-SWAP')} last_close={kl[-1].close} funding_8h={d.get('funding_8h')} oi={d.get('open_interest')} errors={d.get('errors')}")
    except Exception as e:
        print(f"[yellow]FAIL[/yellow] {e}")

    print("\n[bold]Kraken spot candles[/bold]")
    try:
        k = KrakenSpotProvider(instrument=sym)
        kl = k.klines(interval=tf, limit=5)
        print(f"[green]OK[/green] last_close={kl[-1].close}")
    except Exception as e:
        print(f"[yellow]FAIL[/yellow] {e}")

    print("\n[bold]Bybit derivatives snapshot[/bold]")
    try:
        y = BybitDerivativesProvider(symbol=sym)
        d = y.snapshot_derivatives()
        print(f"[green]OK[/green] funding_8h={d.get('funding_8h')} oi={d.get('open_interest')} errors={d.get('errors')}")
    except Exception as e:
        print(f"[yellow]FAIL[/yellow] {e}")


@app.command()
def run_mock(steps: int = 200, seed: int = 7, cfg: str = "config/default.json", journal: str = "data/paper_journal.jsonl"):
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
    c = load_cfg(cfg)

    provider = None
    kl = None

    try:
        provider = BinanceFuturesProvider(symbol=c["instrument"])
        kl = provider.klines(interval=c["timeframe"], limit=limit)
        print("[green]Using Binance Futures candles + derivatives.[/green]")
    except Exception as e:
        print(f"[yellow]Binance Futures failed:[/yellow] {e}")

        try:
            provider = OkxSwapProvider(instrument=c["instrument"])
            kl = provider.klines(interval=c["timeframe"], limit=limit)
            print("[green]Using OKX swap candles + derivatives snapshot.[/green]")
        except Exception as e2:
            print(f"[yellow]OKX swap failed, falling back to Kraken spot candles.[/yellow] {e2}")

            try:
                candle_src = KrakenSpotProvider(instrument=c["instrument"])
                deriv_src = OkxSwapProvider(instrument=c["instrument"])
                provider = CompositeProvider(candles_provider=candle_src, derivatives_provider=deriv_src)
                kl = provider.klines(interval=c["timeframe"], limit=limit)
                print("[green]Using Kraken spot candles + OKX derivatives snapshot.[/green]")
            except Exception as e3:
                print(f"[yellow]Kraken+OKX failed, last resort: Kraken + Bybit derivatives.[/yellow] {e3}")
                candle_src = KrakenSpotProvider(instrument=c["instrument"])
                deriv_src = BybitDerivativesProvider(symbol=c["instrument"])
                provider = CompositeProvider(candles_provider=candle_src, derivatives_provider=deriv_src)
                kl = provider.klines(interval=c["timeframe"], limit=limit)
                print("[green]Using Kraken spot candles + Bybit derivatives snapshot.[/green]")

    sup = Supervisor(provider=provider, cfg=c, journal_path=journal)
    state = State(instrument=c["instrument"], timeframe=c["timeframe"])

    for i, k in enumerate(kl, start=1):
        candle = Candle(ts=k.ts, open=k.open, high=k.high, low=k.low, close=k.close, volume=k.volume)
        state = sup.step(state, candle)
        if i % 50 == 0:
            px = state.market_context.get("price")
            d = state.derivatives or {}
            funding = d.get("funding_8h")
            oi = d.get("open_interest")
            cached = d.get("cached")
            print(f"[{i}/{len(kl)}] price={px:,.0f} funding_8h={funding} oi={oi} cached={cached} setup={state.setup.get('name')} trade_id={state.trade_id}")

    print(f"[green]Done[/green]. Journal: {journal}")


@app.command()
def report(journal: str = "data/paper_journal.jsonl", out_dir: str = "data/reports"):
    """Generate a backtest report + CSV into data/reports/ (permanent on disk)."""
    from .reporting import write_report
    paths = write_report(journal_path=journal, out_dir=out_dir)
    print(f"[green]Wrote report[/green]: {paths['md']}")
    print(f"[green]Wrote trades CSV[/green]: {paths['csv']}")


@app.command()
def journal_tail(n: int = 10, journal: str = "data/paper_journal.jsonl"):
    from .trading import PaperJournal
    j = PaperJournal(journal)
    for e in j.last(n):
        print(e)


if __name__ == "__main__":
    app()
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
    print("Patch applied: lifecycle (expiry/reset) + derivatives caching + report output.")

if __name__ == "__main__":
    main()
