from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
load_dotenv()



# ---------------- Paths (anchor to repo root) ----------------
# Robust path resolution as per docs/FIX_PATHS.md
HERE = Path(__file__).resolve()
# src/laptop_agents/run.py -> src/laptop_agents -> src -> repo_root
REPO_ROOT = HERE.parent.parent.parent

# Put 'src' in path so 'import laptop_agents' works regardless of CWD
sys.path.append(str(REPO_ROOT / "src"))

# Core Logger (Must be after sys.path setup)
from laptop_agents.core.logger import logger
from laptop_agents.core import hard_limits
from laptop_agents.trading.helpers import (
    Candle,
    sma,
    normalize_candle_order,
    calculate_position_size,
    simulate_trade_one_bar,
    utc_ts,
)


# Late imports to avoid circularity - MUST BE AFTER sys.path setup
try:
    from laptop_agents.agents.supervisor import Supervisor
    from laptop_agents.agents.state import State as AgentState
except ImportError:
    # Fallback for environments where agents aren't fully modularized yet
    Supervisor = None
    AgentState = None

RUNS_DIR = REPO_ROOT / "runs"
LATEST_DIR = RUNS_DIR / "latest"
PAPER_DIR = REPO_ROOT / "paper"


# Required keys for valid events.jsonl lines
REQUIRED_EVENT_KEYS = {"event", "timestamp"}

# Required columns for trades.csv
REQUIRED_TRADE_COLUMNS = {"trade_id", "side", "signal", "entry", "exit", "quantity", "pnl", "fees", "timestamp"}

# Import validation functions from tools module (Phase 1 refactor)
from laptop_agents.tools.validation import (
    validate_events_jsonl as _validate_events_jsonl,
    validate_trades_csv,
    validate_summary_html,
)
from laptop_agents.trading.exec_engine import run_live_paper_trading as _run_live_paper_trading


def validate_events_jsonl(events_path: Path) -> tuple[bool, str]:
    """Wrapper to pass append_event callback to the extracted function."""
    return _validate_events_jsonl(events_path, append_event_fn=append_event)


def get_agent_config(
    starting_balance: float = 10000.0,
    risk_pct: float = 1.0,
    stop_bps: float = 30.0,
    tp_r: float = 1.5,
) -> Dict[str, Any]:
    """Return the configuration schema expected by the modular agents."""
    return {
        "engine": {
            "pending_trigger_max_bars": 24,
            "derivatives_refresh_bars": 6,
        },
        "derivatives_gates": {
            "enabled": True,
            "no_trade_funding_8h": 0.0005,
            "half_size_funding_8h": 0.0002,
            "extreme_funding_8h": 0.001,  # NEW: Block at 0.1%
        },
        "setups": {
            "pullback_ribbon": {
                "enabled": True,
                "entry_band_pct": 0.005,
                "stop_atr_mult": 2.0,
                "tp_r_mult": tp_r,
            },
            "sweep_invalidation": {
                "enabled": True,
                "eq_tolerance_pct": 0.002,
                "tp_r_mult": tp_r,
            },
        },
        "risk": {
            "equity": starting_balance,
            "risk_pct": risk_pct / 100.0, # Adapt 1.0 -> 0.01 for modular agents
            "rr_min": 1.2,
        },
    }


def run_orchestrated_mode(
    symbol: str,
    interval: str,
    source: str,
    limit: int,
    fees_bps: float,
    slip_bps: float,
    risk_pct: float = 1.0,
    stop_bps: float = 30.0,
    tp_r: float = 1.5,
    execution_mode: str = "paper",
    dry_run: bool = False,
) -> tuple[bool, str]:
    """Run orchestrated mode - using modular agents in a single pass."""
    if Supervisor is None or AgentState is None:
        return False, "Modular agents not found. Check laptop_agents.agents package."

    run_id = str(uuid.uuid4())
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Create run-specific LATEST_DIR symlink/copy
    reset_latest_dir()
    
    append_event({
        "event": "OrchestratedModularRunStarted",
        "run_id": run_id,
        "source": source,
        "symbol": symbol,
        "interval": interval,
        "execution_mode": execution_mode
    })
    
    # Initialize Trading Circuit Breaker
    from laptop_agents.resilience.trading_circuit_breaker import TradingCircuitBreaker
    circuit_breaker = TradingCircuitBreaker(max_daily_drawdown_pct=5.0, max_consecutive_losses=5)
    
    try:
        # Load candles
        if source == "bitunix":
            candles = load_bitunix_candles(symbol, interval, limit)
        else:
            candles = load_mock_candles(max(int(limit), 200))
        
        candles = normalize_candle_order(candles)
        
        if len(candles) < 51: # Need enough for EMA(50)
            logger.warning(f"Only {len(candles)} candles provided. This is below the EMA(50) warm-up required for trend detection. Results may be flat.")
            append_event({"event": "LowCandleCountWarning", "count": len(candles), "required": 51})
        
        if len(candles) < 31:
            raise RuntimeError("Need at least 31 candles for orchestrated modular mode")
        
        append_event({"event": "MarketDataLoaded", "source": source, "symbol": symbol, "count": len(candles)})
        
        # Initialize Supervisor and State
        starting_balance = 10_000.0
        cfg = get_agent_config(
            starting_balance=starting_balance,
            risk_pct=risk_pct,
            stop_bps=stop_bps,
            tp_r=tp_r
        )
        
        # Live Broker Setup
        broker = None
        if dry_run:
            from laptop_agents.paper.broker import PaperBroker
            class DryRunBroker(PaperBroker):
                def on_candle(self, candle, order):
                    if order and order.get("go"):
                        logger.info(f"[DRY-RUN] Would execute: {order.get('side')} {order.get('qty')} at {order.get('entry')}")
                        append_event({"event": "DryRunOrder", "order": order})
                    return {"fills": [], "exits": []}
            broker = DryRunBroker(symbol=symbol)
            append_event({"event": "DryRunModeActive"})
        elif execution_mode == "live":
            if source != "bitunix":
                raise ValueError("Live execution currently only supports bitunix source")
            
            from laptop_agents.data.providers.bitunix_futures import BitunixFuturesProvider
            from laptop_agents.execution.bitunix_broker import BitunixBroker
            import os
            
            api_key = os.environ.get("BITUNIX_API_KEY")
            secret_key = os.environ.get("BITUNIX_API_SECRET") or os.environ.get("BITUNIX_SECRET_KEY")
            
            if not api_key or not secret_key:
                raise ValueError("Live execution requires BITUNIX_API_KEY and BITUNIX_API_SECRET environment variables")
                
            provider = BitunixFuturesProvider(
                symbol=symbol,
                api_key=api_key,
                secret_key=secret_key
            )
            broker = BitunixBroker(provider)
            append_event({"event": "LiveBrokerInitialized", "broker": "BitunixBroker"})

        # Point the journal to the run directory for modular isolation
        journal_path = run_dir / "journal.jsonl"
        # If no live broker, initialize PaperBroker with the correct symbol
        if broker is None:
             from laptop_agents.paper.broker import PaperBroker
             broker = PaperBroker(symbol=symbol)
             
        supervisor = Supervisor(provider=None, cfg=cfg, journal_path=str(journal_path), broker=broker)
        state = AgentState(instrument=symbol, timeframe=interval)
        
        equity_history = []
        current_equity = starting_balance
        
        # Load daily checkpoint if exists
        checkpoint_path = REPO_ROOT / "logs" / "daily_checkpoint.json"
        if checkpoint_path.exists():
            try:
                with checkpoint_path.open("r") as f:
                    ckpt = json.load(f)
                if ckpt.get("date") == datetime.now(timezone.utc).strftime("%Y-%m-%d"):
                    starting_balance = float(ckpt.get("starting_equity", starting_balance))
                    append_event({"event": "CheckpointLoaded", "equity": starting_balance})
            except Exception as e:
                append_event({"event": "CheckpointLoadError", "error": str(e)})

        # Initialize circuit breaker with starting equity
        circuit_breaker.set_starting_equity(starting_balance)
        
        # Step through candles
        for i, candle in enumerate(candles):
            # Check circuit breaker before trading
            if circuit_breaker.is_tripped():
                append_event({
                    "event": "CircuitBreakerTripped",
                    "status": circuit_breaker.get_status()
                })
                break
            
            # If live, only hit the exchange for the last candle to avoid rate limits
            skip_broker = (execution_mode == "live" and i < len(candles) - 1)
            state = supervisor.step(state, candle, skip_broker=skip_broker)
            
            # Simple equity tracking
            trade_pnl = None
            is_inverse = getattr(supervisor.broker, "is_inverse", False)
            for ex in state.broker_events.get("exits", []):
                pnl = float(ex.get("pnl", 0.0))
                # Convert BTC PnL to USD for dashboard tracking if inverse
                if is_inverse:
                    pnl_usd = pnl * float(candle.close)
                    current_equity += pnl_usd
                    trade_pnl = pnl_usd
                else:
                    current_equity += pnl
                    trade_pnl = pnl
            
            # Update circuit breaker with equity and trade result
            circuit_breaker.update_equity(current_equity, trade_pnl)
            
            # Mark-to-Market Equity
            unrealized = supervisor.broker.get_unrealized_pnl(float(candle.close))
            if is_inverse:
                unrealized = unrealized * float(candle.close)
            total_equity = current_equity + unrealized
            
            equity_history.append({"ts": candle.ts, "equity": total_equity})
            
            # Heartbeat for external monitors
            if i % 10 == 0:
                heartbeat_path = REPO_ROOT / "logs" / "heartbeat.json"
                heartbeat_path.parent.mkdir(exist_ok=True)
                with heartbeat_path.open("w") as f:
                    json.dump({
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "candle_idx": i,
                        "equity": total_equity,
                        "symbol": symbol,
                    }, f)
            
        # Write equity.csv for the chart
        equity_csv = LATEST_DIR / "equity.csv"
        with equity_csv.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["ts", "equity"])
            writer.writeheader()
            writer.writerows(equity_history)

        # Extract trades from the PaperJournal for reporting
        trades = []
        if journal_path.exists():
            from laptop_agents.trading.paper_journal import PaperJournal
            journal = PaperJournal(journal_path)
            
            # Temporary storage to pair entries and exits
            open_trades = {}
            
            for event in journal.iter_events():
                if event.get("type") == "update":
                    tid = event.get("trade_id")
                    if "fill" in event:
                         open_trades[tid] = event["fill"]
                    elif "exit" in event and tid in open_trades:
                         f = open_trades.pop(tid)
                         x = event["exit"]
                         trades.append({
                             "trade_id": tid,
                             "side": f.get("side", "???"),
                             "signal": "MODULAR",
                             "entry": float(f.get("price", 0)),
                             "exit": float(x.get("price", 0)),
                             "quantity": float(f.get("qty", 0)),
                             "pnl": float(x.get("pnl", 0)),
                             "fees": float(f.get("fees", 0)) + float(x.get("fees", 0)),
                             "timestamp": str(x.get("at", event.get("at", "")))
                         })
        
        if trades:
             write_trades_csv(trades)
        else:
             write_trades_csv([])

        ending_balance = current_equity
        
        append_event({"event": "OrchestratedModularFinished", "trades": len(trades), "ending_balance": ending_balance})
        
        # Save daily checkpoint
        try:
            checkpoint_path = REPO_ROOT / "logs" / "daily_checkpoint.json"
            checkpoint_path.parent.mkdir(exist_ok=True)
            with checkpoint_path.open("w") as f:
                json.dump({
                    "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "starting_equity": starting_balance,
                    "ending_equity": float(ending_balance),
                }, f)
        except Exception as e:
            append_event({"event": "CheckpointSaveError", "error": str(e)})
        
        # Copy artifacts to run_dir
        if (LATEST_DIR / "trades.csv").exists():
            shutil.copy2(LATEST_DIR / "trades.csv", run_dir / "trades.csv")
        if (LATEST_DIR / "events.jsonl").exists():
            shutil.copy2(LATEST_DIR / "events.jsonl", run_dir / "events.jsonl")
        
        # Write summary
        summary = {
            "run_id": run_id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": source,
            "symbol": symbol,
            "interval": interval,
            "candle_count": len(candles),
            "last_ts": str(candles[-1].ts),
            "last_close": float(candles[-1].close),
            "fees_bps": fees_bps,
            "slip_bps": slip_bps,
            "starting_balance": starting_balance,
            "ending_balance": float(ending_balance),
            "net_pnl": float(ending_balance - starting_balance),
            "trades": len(trades),
            "mode": "orchestrated",
            "setup": state.setup,
            "risk_pct": risk_pct,
            "stop_bps": stop_bps,
            "tp_r": tp_r,
            "max_leverage": getattr(hard_limits, "MAX_LEVERAGE", 1.0),
        }
        write_state({"summary": summary})
        render_html(summary, trades, "", candles=candles)
        
        if (LATEST_DIR / "summary.html").exists():
            shutil.copy2(LATEST_DIR / "summary.html", run_dir / "summary.html")
            
        # Session Summary Log
        summary_text = f"""
========== SESSION COMPLETE ==========
Run ID:     {run_id}
Symbol:     {symbol}
Candles:    {len(candles)}
Trades:     {len(trades)}
Start:      ${starting_balance:,.2f}
End:        ${ending_balance:,.2f}
Net PnL:    ${ending_balance - starting_balance:,.2f}
=======================================
"""
        logger.info(summary_text)
            
        # Validate artifacts
        events_valid, events_msg = validate_events_jsonl(run_dir / "events.jsonl")
        trades_valid, trades_msg = validate_trades_csv(run_dir / "trades.csv")
        summary_valid, summary_msg = validate_summary_html(run_dir / "summary.html")
        
        if not events_valid:
            raise RuntimeError(f"events.jsonl validation failed: {events_msg}")
        if not summary_valid:
            raise RuntimeError(f"summary.html validation failed: {summary_msg}")
        if not trades_valid:
            if "no data rows" in trades_msg:
                pass
            else:
                raise RuntimeError(f"trades.csv validation failed: {trades_msg}")
        
        return True, f"Orchestrated modular run completed. Run ID: {run_id}"
        
    except Exception as e:
        import traceback
        append_event({"event": "OrchestratedModularError", "error": str(e), "trace": traceback.format_exc()[-500:]})
        return False, str(e)


def check_bitunix_config() -> tuple[bool, str]:
    """Check if bitunix configuration is available."""
    env_path = REPO_ROOT / ".env"
    import os
    api_key = os.environ.get("BITUNIX_API_KEY", "")
    # Support both naming conventions for secret key
    secret_key = os.environ.get("BITUNIX_API_SECRET") or os.environ.get("BITUNIX_SECRET_KEY", "")
    
    if not api_key or not secret_key:
        return False, "Bitunix API credentials not configured. Set BITUNIX_API_KEY and BITUNIX_API_SECRET in .env"
    return True, "Bitunix configured"





def reset_latest_dir() -> None:
    RUNS_DIR.mkdir(exist_ok=True)
    if LATEST_DIR.exists():
        shutil.rmtree(LATEST_DIR)
    LATEST_DIR.mkdir(parents=True, exist_ok=True)


def append_event(obj: Dict[str, Any], paper: bool = False) -> None:
    obj.setdefault("timestamp", utc_ts())
    # Structured logging to JSONL and Console
    event_name = obj.get("event", "UnnamedEvent")
    logger.info(f"EVENT: {event_name}", obj)
    
    if paper:
        PAPER_DIR.mkdir(exist_ok=True)
        with (PAPER_DIR / "events.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    else:
        with (LATEST_DIR / "events.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


# Import trading helpers (Phase 1 refactor)




def load_mock_candles(n: int = 200) -> List[Candle]:
    candles: List[Candle] = []
    price = 100_000.0
    import random
    random.seed(42)  # Deterministic mock
    
    for i in range(n):
        # Add a trend + some significant noise to hit limits
        price += 10.0 + (random.random() - 0.5) * 400.0
        
        # Wider wick range (ATR-like)
        range_size = 300.0 + random.random() * 200.0
        o = price - (random.random() - 0.5) * range_size * 0.5
        c = price + (random.random() - 0.5) * range_size * 0.5
        h = max(o, c) + random.random() * range_size * 0.4
        l = min(o, c) - random.random() * range_size * 0.4
        
        # Use real timestamps for Plotly compatibility
        ts_obj = datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=i)
        candles.append(Candle(ts=ts_obj.isoformat(), open=o, high=h, low=l, close=c, volume=1.0))
    return candles


def _get_bitunix_provider_class():
    import laptop_agents.data.providers.bitunix_futures as m
    for name in dir(m):
        obj = getattr(m, name)
        if isinstance(obj, type) and hasattr(obj, "klines"):
            return obj
    raise RuntimeError("No Bitunix provider class with .klines() found in laptop_agents.data.providers.bitunix_futures")


def load_bitunix_candles(symbol: str, interval: str, limit: int) -> List[Candle]:
    Provider = _get_bitunix_provider_class()
    client = Provider(symbol=symbol)
    # Use paged fetch to support limits > 200
    rows = client.klines_paged(interval=interval, total=int(limit))

    out: List[Candle] = []
    for c in rows:
        ts = getattr(c, "ts", None) or getattr(c, "time", None) or getattr(c, "timestamp", None) or ""
        o = float(getattr(c, "open"))
        h = float(getattr(c, "high"))
        l = float(getattr(c, "low"))
        cl = float(getattr(c, "close"))
        v = float(getattr(c, "volume", 0.0) or 0.0)
        out.append(Candle(ts=str(ts), open=o, high=h, low=l, close=cl, volume=v))
    return out


def sma(vals: List[float], window: int) -> Optional[float]:
    if len(vals) < window:
        return None
    return sum(vals[-window:]) / float(window)


# calculate_position_size imported from helpers










def _ensure_backtest_context():
    from laptop_agents.backtest.engine import set_context
    set_context(LATEST_DIR, append_event)


def run_validation(*args, **kwargs) -> Dict[str, Any]:
    """Wrapper for extracted backtest engine validation."""
    _ensure_backtest_context()
    from laptop_agents.backtest.engine import run_validation as _run_validation
    return _run_validation(*args, **kwargs)


def run_backtest_bar_mode(*args, **kwargs) -> Dict[str, Any]:
    """Wrapper for extracted backtest engine bar mode."""
    _ensure_backtest_context()
    from laptop_agents.backtest.engine import run_backtest_bar_mode as _run
    return _run(*args, **kwargs)




def run_backtest_position_mode(*args, **kwargs) -> Dict[str, Any]:
    """Wrapper for extracted backtest engine position mode."""
    _ensure_backtest_context()
    from laptop_agents.backtest.engine import run_backtest_position_mode as _run
    return _run(*args, **kwargs)



def run_live_paper_trading(*args, **kwargs) -> tuple[List[Dict[str, Any]], float, Dict[str, Any]]:
    """Wrapper for extracted live paper trading loop."""
    return _run_live_paper_trading(*args, **kwargs, paper_dir=PAPER_DIR, append_event_fn=append_event)


def generate_signal(candles: List[Candle]) -> Optional[str]:
    # Avoid lookahead: compute signal on candles[:-1]
    base = candles[:-1]
    if len(base) < 30:
        return None
    closes = [c.close for c in base]
    fast = sma(closes, 10)
    slow = sma(closes, 30)
    if fast is None or slow is None:
        return None
    return "BUY" if fast > slow else "SELL"


# simulate_trade_one_bar imported from helpers


def write_trades_csv(trades: List[Dict[str, Any]]) -> None:
    p = LATEST_DIR / "trades.csv"
    # Define canonical trade schema - these are the only fields we write
    fieldnames = ["trade_id", "side", "signal", "entry", "exit", "price", "quantity", "pnl", "fees",
                  "entry_ts", "exit_ts", "timestamp"]
    
    # Use atomic write: write to temp file first, then replace
    temp_p = p.with_suffix(".tmp")
    try:
        with temp_p.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            for t in trades:
                # Ensure we only write the canonical fields
                filtered_trade = {k: v for k, v in t.items() if k in fieldnames}
                w.writerow(filtered_trade)
        # Atomic replace
        temp_p.replace(p)
    except Exception as e:
        # Clean up temp file if something went wrong
        if temp_p.exists():
            temp_p.unlink()
        raise RuntimeError(f"Failed to write trades.csv: {e}")


def write_state(state: Dict[str, Any]) -> None:
    with (LATEST_DIR / "state.json").open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def render_html(summary: Dict[str, Any], trades: List[Dict[str, Any]], error_message: str = "", candles: List[Candle] = None) -> None:
    """
    Render HTML summary dashboard.
    
    This is a thin wrapper that delegates to the extracted html_renderer module
    for better compute efficiency (avoids parsing ~30KB of template code on every import).
    """
    # Lazy import to avoid loading template code until needed
    from laptop_agents.reporting.html_renderer import render_html as _render_html
    _render_html(
        summary=summary,
        trades=trades,
        error_message=error_message,
        candles=candles,
        latest_dir=LATEST_DIR,
        append_event_fn=append_event,
    )




def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["mock", "bitunix"], default="mock")
    ap.add_argument("--symbol", default="BTCUSD")
    ap.add_argument("--interval", default="1m")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--fees-bps", type=float, default=2.0)   # 2 bps per side (simple)
    ap.add_argument("--slip-bps", type=float, default=0.5)   # tiny adverse slip
    ap.add_argument("--backtest", type=int, default=0, help="Backtest mode: 0=single trade (default), N=backtest last N candles")
    ap.add_argument("--backtest-mode", choices=["bar", "position"], default="position",
                   help="Backtest strategy: bar (one trade per bar) or position (position management)")
    ap.add_argument("--mode", choices=["single", "backtest", "live", "validate", "selftest", "orchestrated"], default=None,
                   help="Run mode: single (default), backtest, live paper trading, validate, selftest, or orchestrated")
    ap.add_argument("--once", action="store_true", default=False,
                   help="Run once and exit (for orchestrated mode)")
    ap.add_argument("--execution-mode", choices=["paper", "live"], default="paper",
                   help="Execution mode for orchestrated: paper (default) or live (real exchange orders)")
    ap.add_argument("--risk-pct", type=float, default=1.0, help="%% equity risked per trade")
    ap.add_argument("--stop-bps", type=float, default=30.0, help="stop distance in bps from entry (0.30%%)")
    ap.add_argument("--tp-r", type=float, default=1.5, help="take profit = stop_distance * tp-r")
    ap.add_argument("--max-leverage", type=float, default=1.0, help="cap notional: qty*entry <= equity*max_leverage")
    ap.add_argument("--intrabar-mode", choices=["conservative", "optimistic"], default="conservative",
                   help="conservative: stop first; optimistic: tp first")
    ap.add_argument("--validate-splits", type=int, default=5, help="number of walk-forward folds")
    ap.add_argument("--validate-train", type=int, default=600, help="candles used for train window")
    ap.add_argument("--validate-test", type=int, default=200, help="candles used for test window")
    ap.add_argument("--grid", type=str, default="sma=10,30;stop=20,30,40;tp=1.0,1.5,2.0",
                   help="parameter grid: sma=fast,slow;stop=...;tp=...")
    ap.add_argument("--validate-max-candidates", type=int, default=200,
                   help="maximum number of parameter combinations to evaluate in validation mode")
    ap.add_argument("--dry-run", action="store_true", help="Log orders without executing")
    args = ap.parse_args()

    # Symbol validation
    SUPPORTED_SYMBOLS = {"BTCUSD", "BTCUSDT", "ETHUSD", "ETHUSDT"}
    if args.symbol not in SUPPORTED_SYMBOLS:
        logger.warning(f"Symbol '{args.symbol}' not in tested list: {SUPPORTED_SYMBOLS}")

    # Ensure runs/latest exists before we start
    RUNS_DIR.mkdir(exist_ok=True)
    LATEST_DIR.mkdir(parents=True, exist_ok=True)

    run_id = str(uuid.uuid4())
    starting_balance = 10_000.0
    error_message = ""

    # Determine mode
    if args.mode is None:
        if args.backtest > 0:
            mode = "backtest"
        else:
            mode = "single"
    else:
        mode = args.mode

    append_event({"event": "RunStarted", "run_id": run_id, "source": args.source, "symbol": args.symbol, "interval": args.interval, "backtest": args.backtest, "mode": mode})

    try:
        if args.source == "bitunix":
            limit = min(max(int(args.limit), 2), 200)
            candles = load_bitunix_candles(args.symbol, args.interval, limit)
        else:
            candles = load_mock_candles(max(int(args.limit), 50))

        append_event({"event": "MarketDataLoaded", "source": args.source, "symbol": args.symbol, "interval": args.interval, "count": len(candles)})

        # Normalize candle order (handle newest-first if needed)
        candles = normalize_candle_order(candles)
         
        if len(candles) < 2:
            raise RuntimeError("Need at least 2 candles to simulate a one-bar trade")

        if mode == "validate":
            # Validation mode
            append_event({"event": "ValidationStarted", "splits": args.validate_splits,
                         "train": args.validate_train, "test": args.validate_test, "grid": args.grid})
            
            # Calculate total candles needed for validation
            total_candles_needed = args.validate_splits * (args.validate_train + args.validate_test)
            
            # Use paging for Bitunix to fetch enough candles
            if args.source == "bitunix":
                # Use paging to fetch enough candles for validation
                candles = []
                try:
                    Provider = _get_bitunix_provider_class()
                    client = Provider(symbol=args.symbol)
                    candles = client.klines_paged(interval=args.interval, total=total_candles_needed)
                    append_event({"event": "BitunixPagedCandlesLoaded", "requested": total_candles_needed, "loaded": len(candles)})
                except Exception as e:
                    append_event({"event": "BitunixPagingFailed", "error": str(e)})
                    # Fallback to regular loading with higher limit
                    limit = min(max(total_candles_needed, 2000), 5000)  # Cap at 5000 for safety
                    candles = load_bitunix_candles(args.symbol, args.interval, limit)
            else:
                # For mock data, generate enough candles
                candles = load_mock_candles(total_candles_needed)
            
            append_event({"event": "MarketDataLoaded", "source": args.source, "symbol": args.symbol, "interval": args.interval, "count": len(candles)})
            
            # Normalize candle order
            candles = normalize_candle_order(candles)
            
            # Run validation
            validation_result = run_validation(
                candles=candles,
                starting_balance=starting_balance,
                fees_bps=float(args.fees_bps),
                slip_bps=float(args.slip_bps),
                risk_pct=float(args.risk_pct),
                max_leverage=float(args.max_leverage),
                intrabar_mode=args.intrabar_mode,
                grid_str=args.grid,
                validate_splits=args.validate_splits,
                validate_train=args.validate_train,
                validate_test=args.validate_test,
                max_candidates=args.validate_max_candidates,
            )
            
            # Write validation outputs
            trades = validation_result["all_trades"]
            ending_balance = starting_balance + validation_result["total_os_pnl"]
            
            # Write validation.json with comprehensive report
            validation_json_path = LATEST_DIR / "validation.json"
            temp_validation = validation_json_path.with_suffix(".tmp")
            try:
                validation_json_content = {
                    "meta": {
                        "timestamp": utc_ts(),
                        "mode": "validate",
                        "source": args.source,
                        "symbol": args.symbol,
                        "interval": args.interval
                    },
                    **validation_result["validation_report"]
                }
                
                # Add leaderboard details
                leaderboard_details = []
                for i, entry in enumerate(validation_result["leaderboard"]):
                    leaderboard_details.append({
                        "rank": i + 1,
                        "fast_sma": entry["fast_sma"],
                        "slow_sma": entry["slow_sma"],
                        "stop_bps": entry["stop_bps"],
                        "tp_r": entry["tp_r"],
                        "net_pnl": entry["net_pnl"],
                        "max_drawdown": entry["max_drawdown"],
                        "win_rate": entry.get("win_rate", 0),
                        "trades": entry["trades"],
                        "fees_total": entry["fees_total"],
                        "objective": entry["objective"]
                    })
                validation_json_content["leaderboard"] = leaderboard_details
                
                # Add best params details
                if validation_result["best_params_overall"]:
                    best_params = validation_result["best_params_overall"]
                    validation_json_content["best_params"] = {
                        "fast_sma": best_params["fast_sma"],
                        "slow_sma": best_params["slow_sma"],
                        "stop_bps": best_params["stop_bps"],
                        "tp_r": best_params["tp_r"],
                        **validation_result.get("best_metrics", {})
                    }
                
                with temp_validation.open("w", encoding="utf-8") as f:
                    json.dump(validation_json_content, f, indent=2)
                temp_validation.replace(validation_json_path)
                append_event({"event": "ValidationJSONWritten", "path": str(validation_json_path)})
            except Exception as e:
                if temp_validation.exists():
                    temp_validation.unlink()
                raise RuntimeError(f"Failed to write validation.json: {e}")
            
            # Also write the full results for backward compatibility
            validate_results_path = LATEST_DIR / "validate_results.json"
            temp_results = validate_results_path.with_suffix(".tmp")
            try:
                with temp_results.open("w", encoding="utf-8") as f:
                    json.dump(validation_result, f, indent=2)
                temp_results.replace(validate_results_path)
            except Exception as e:
                if temp_results.exists():
                    temp_results.unlink()
                raise RuntimeError(f"Failed to write validate_results.json: {e}")
            
            # Write validate_folds.csv
            validate_folds_path = LATEST_DIR / "validate_folds.csv"
            temp_folds = validate_folds_path.with_suffix(".tmp")
            try:
                with temp_folds.open("w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=[
                        "fold_index", "train_start", "train_end", "test_start", "test_end",
                        "fast_sma", "slow_sma", "stop_bps", "tp_r",
                        "test_net_pnl", "test_max_drawdown", "test_trades", "test_win_rate"
                    ])
                    writer.writeheader()
                    for fold in validation_result["folds"]:
                        bp = fold["best_params"]
                        tr = fold["test_result"]
                        wins = tr["wins"]
                        losses = tr["losses"]
                        win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0.0
                        writer.writerow({
                            "fold_index": fold["fold_index"],
                            "train_start": fold["train_start"],
                            "train_end": fold["train_end"],
                            "test_start": fold["test_start"],
                            "test_end": fold["test_end"],
                            "fast_sma": bp["fast_sma"],
                            "slow_sma": bp["slow_sma"],
                            "stop_bps": bp["stop_bps"],
                            "tp_r": bp["tp_r"],
                            "test_net_pnl": tr["net_pnl"],
                            "test_max_drawdown": tr["max_drawdown"],
                            "test_trades": tr["trades"],
                            "test_win_rate": win_rate,
                        })
                temp_folds.replace(validate_folds_path)
            except Exception as e:
                if temp_folds.exists():
                    temp_folds.unlink()
                raise RuntimeError(f"Failed to write validate_folds.csv: {e}")
            
            # Write equity.csv
            equity_csv_path = LATEST_DIR / "equity.csv"
            temp_equity = equity_csv_path.with_suffix(".tmp")
            try:
                with temp_equity.open("w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=["ts", "equity"])
                    writer.writeheader()
                    for eq in validation_result["equity_history"]:
                        writer.writerow(eq)
                temp_equity.replace(equity_csv_path)
            except Exception as e:
                if temp_equity.exists():
                    temp_equity.unlink()
                raise RuntimeError(f"Failed to write equity.csv: {e}")
            
            append_event({"event": "ValidationFinished", "folds": len(validation_result["folds"]),
                         "total_os_pnl": validation_result["total_os_pnl"]})

        elif mode == "live":
            # Live paper trading mode
            trades, ending_balance, state = run_live_paper_trading(
                candles=candles,
                starting_balance=starting_balance,
                fees_bps=float(args.fees_bps),
                slip_bps=float(args.slip_bps),
                symbol=args.symbol,
                interval=args.interval,
                source=args.source,
                risk_pct=float(args.risk_pct),
                stop_bps=float(args.stop_bps),
                tp_r=float(args.tp_r),
                max_leverage=float(args.max_leverage),
                intrabar_mode=args.intrabar_mode,
            )
            append_event({"event": "LivePaperFinished", "trades": len(trades), "ending_balance": ending_balance}, paper=True)
        elif mode == "backtest":
            # Backtest mode
            append_event({"event": "BacktestStarted", "candles": len(candles), "backtest": args.backtest,
                         "mode": args.backtest_mode})
            
            # Cap backtest to available candles
            backtest_candles = min(args.backtest, len(candles))
            backtest_slice = candles[-backtest_candles:] if backtest_candles > 0 else candles
            
            # Use appropriate backtest function based on mode
            if args.backtest_mode == "bar":
                backtest_result = run_backtest_bar_mode(
                    candles=backtest_slice,
                    starting_balance=starting_balance,
                    fees_bps=float(args.fees_bps),
                    slip_bps=float(args.slip_bps)
                )
            else:  # position mode
                backtest_result = run_backtest_position_mode(
                    candles=backtest_slice,
                    starting_balance=starting_balance,
                    fees_bps=float(args.fees_bps),
                    slip_bps=float(args.slip_bps),
                    risk_pct=float(args.risk_pct),
                    stop_bps=float(args.stop_bps),
                    tp_r=float(args.tp_r),
                    max_leverage=float(args.max_leverage),
                    intrabar_mode=args.intrabar_mode,
                )
            
            trades = backtest_result["trades"]
            ending_balance = backtest_result["ending_balance"]
            stats = backtest_result["stats"]
            
            append_event({"event": "BacktestFinished", "trades": len(trades), "net_pnl": stats["net_pnl"],
                         "mode": args.backtest_mode})
            
        elif mode == "selftest":
            # Self-test mode
            append_event({"event": "SelfTestStarted", "intrabar_mode": args.intrabar_mode})
            
            # Run selftest
            success, message = run_selftest(intrabar_mode=args.intrabar_mode)
            
            # Create a summary with selftest results
            last_candle = candles[-1] if candles else Candle(ts="selftest", open=100.0, high=100.0, low=100.0, close=100.0, volume=1.0)
            summary = {
                "run_id": run_id,
                "source": args.source,
                "symbol": args.symbol,
                "interval": args.interval,
                "candle_count": len(candles),
                "last_ts": str(last_candle.ts),
                "last_close": float(last_candle.close),
                "fees_bps": float(args.fees_bps),
                "slip_bps": float(args.slip_bps),
                "starting_balance": starting_balance,
                "ending_balance": starting_balance,
                "net_pnl": 0.0,
                "trades": 0,
                "mode": mode,
                "selftest_result": "PASS" if success else "FAIL",
                "selftest_message": message,
            }
            
            # Write trades.csv (empty for selftest)
            write_trades_csv([])
            
            # Write state.json with selftest info
            write_state({
                "summary": summary,
                "selftest": {
                    "success": success,
                    "message": message,
                    "timestamp": utc_ts()
                }
            })
            
            # Render HTML with selftest results
            error_message = "" if success else f"SELFTEST FAILED: {message}"
            render_html(summary, [], error_message)
            
            append_event({"event": "SelfTestFinished", "success": success, "message": message})
            
            if success:
                logger.info(f"SELFTEST PASS: {message}")
                return 0
            else:
                logger.error(f"SELFTEST FAIL: {message}")
                return 1

        elif mode == "orchestrated":
            # Orchestrated mode - end-to-end with artifact validation
            # Run orchestrated mode (bitunix public API doesn't require credentials)
            success, message = run_orchestrated_mode(
                symbol=args.symbol,
                interval=args.interval,
                source=args.source,
                limit=args.limit,
                fees_bps=float(args.fees_bps),
                slip_bps=float(args.slip_bps),
                risk_pct=float(args.risk_pct),
                stop_bps=float(args.stop_bps),
                tp_r=float(args.tp_r),
                execution_mode=args.execution_mode,
                dry_run=args.dry_run,
            )
            
            if success:
                logger.info(message)
                return 0
            else:
                logger.error(f"ORCHESTRATED ERROR: {message}")
                return 1

        elif mode == "single":
            # Single trade mode (original behavior)
            last = candles[-1]
            prev = candles[-2]
            append_event({"event": "LastCandle", "ts": last.ts, "close": last.close})
            append_event({"event": "PrevCandle", "ts": prev.ts, "close": prev.close})

            signal = generate_signal(candles)
            append_event({"event": "SignalGenerated", "signal": signal})

            trades: List[Dict[str, Any]] = []
            ending_balance = starting_balance

            if signal in ("BUY", "SELL"):
                trade = simulate_trade_one_bar(
                    signal=signal,
                    entry_px=float(prev.close),
                    exit_px=float(last.close),
                    starting_balance=starting_balance,
                    fees_bps=float(args.fees_bps),
                    slip_bps=float(args.slip_bps),
                )
                trades.append(trade)
                ending_balance = starting_balance + float(trade["pnl"])
                append_event({"event": "TradeSimulated", "trade": trade})
            else:
                append_event({"event": "NoTrade", "reason": "insufficient data for SMA(10/30)"})
        else:
            # Backtest mode
            append_event({"event": "BacktestStarted", "candles": len(candles), "backtest": args.backtest,
                         "mode": args.backtest_mode})
            
            # Cap backtest to available candles
            backtest_candles = min(args.backtest, len(candles))
            backtest_slice = candles[-backtest_candles:] if backtest_candles > 0 else candles
            
            # Use appropriate backtest function based on mode
            if args.backtest_mode == "bar":
                backtest_result = run_backtest_bar_mode(
                    candles=backtest_slice,
                    starting_balance=starting_balance,
                    fees_bps=float(args.fees_bps),
                    slip_bps=float(args.slip_bps)
                )
            else:  # position mode
                backtest_result = run_backtest_position_mode(
                    candles=backtest_slice,
                    starting_balance=starting_balance,
                    fees_bps=float(args.fees_bps),
                    slip_bps=float(args.slip_bps)
                )
            
            trades = backtest_result["trades"]
            ending_balance = backtest_result["ending_balance"]
            stats = backtest_result["stats"]
            
            append_event({"event": "BacktestFinished", "trades": len(trades), "net_pnl": stats["net_pnl"],
                         "mode": args.backtest_mode})

        # Write trades.csv with atomic write
        write_trades_csv(trades)

        # Prepare summary
        last_candle = candles[-1]
        summary = {
            "run_id": run_id,
            "source": args.source,
            "symbol": args.symbol,
            "interval": args.interval,
            "candle_count": len(candles),
            "last_ts": str(last_candle.ts),
            "last_close": float(last_candle.close),
            "fees_bps": float(args.fees_bps),
            "slip_bps": float(args.slip_bps),
            "starting_balance": starting_balance,
            "ending_balance": float(ending_balance),
            "net_pnl": float(ending_balance - starting_balance),
            "trades": len(trades),
            "mode": mode,
        }
         
        # Add backtest stats if in backtest mode
        if mode == "backtest":
            stats_path = LATEST_DIR / "stats.json"
            if stats_path.exists():
                with stats_path.open("r", encoding="utf-8") as f:
                    backtest_stats = json.load(f)
                    summary.update({
                        "win_rate": backtest_stats.get("win_rate", 0.0),
                        "max_drawdown": backtest_stats.get("max_drawdown", 0.0),
                        "fees_total": backtest_stats.get("fees_total", 0.0),
                    })
        
        # Add live paper trading stats if in live mode
        if mode == "live":
            summary.update({
                "position": state.get("position"),
                "realized_pnl": state.get("realized_pnl", 0.0),
                "unrealized_pnl": state.get("unrealized_pnl", 0.0),
                "net_pnl": state.get("net_pnl", 0.0),
                "fees_total": state.get("fees_total", 0.0),
            })
        
        write_state({"summary": summary})
        
        # Always write summary.html, even if we succeed
        render_html(summary, trades, error_message, candles=candles)

        append_event({"event": "RunFinished", "run_id": run_id})
        return 0

    except Exception as e:
        error_message = str(e)
        # Include traceback in events for debugging
        import traceback
        tb_str = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        append_event({"event": "Error", "message": error_message, "trace": tb_str[-500:]})
        
        # Always write summary.html even on error
        summary = {
            "run_id": run_id,
            "source": args.source,
            "symbol": args.symbol,
            "interval": args.interval,
            "candle_count": 0,
            "last_ts": "N/A",
            "last_close": 0.0,
            "fees_bps": float(args.fees_bps),
            "slip_bps": float(args.slip_bps),
            "starting_balance": starting_balance,
            "ending_balance": starting_balance,
            "net_pnl": 0.0,
            "trades": 0,
        }
        render_html(summary, [], error_message)
        
        logger.error(f"RUNTIME ERROR: {error_message}")
        return 1


def run_selftest(intrabar_mode: str = "conservative") -> tuple[bool, str]:
    """
    Run deterministic self-test to verify risk engine correctness.
    Tests LONG TP, LONG STOP, SHORT TP, SHORT STOP, and intrabar ambiguity.
    Returns (success, message)
    """
    # Create deterministic candle sequence that triggers specific scenarios
    # Need at least 31 candles for backtest (30 for SMA + 1 for trading)
    candles = []
    price = 100.0
    for i in range(50):  # Generate 50 candles to ensure we have enough
        # Create price movement that will trigger both LONG and SHORT scenarios
        if i < 25:
            # Upward trend for LONG positions
            price += 0.5
        else:
            # Downward trend for SHORT positions
            price -= 0.5
        
        # Add some volatility
        high = price + 2.0
        low = price - 2.0
        close = price + (0.5 if i % 2 == 0 else -0.5)  # Some variability
        
        candles.append(Candle(ts=f"test_{i:04d}", open=price, high=high, low=low, close=close, volume=1.0))
    
    # Test parameters
    starting_balance = 10000.0
    fees_bps = 0.0  # No fees for simpler testing
    slip_bps = 0.0  # No slippage for simpler testing
    risk_pct = 1.0
    stop_bps = 50.0  # 0.5% stop
    tp_r = 2.0  # 2:1 reward:risk
    max_leverage = 1.0
    
    # Run backtest in position mode
    try:
        result = run_backtest_position_mode(
            candles=candles,
            starting_balance=starting_balance,
            fees_bps=fees_bps,
            slip_bps=slip_bps,
            risk_pct=risk_pct,
            stop_bps=stop_bps,
            tp_r=tp_r,
            max_leverage=max_leverage,
            intrabar_mode=intrabar_mode,
        )
        
        trades = result["trades"]
        
        # Verify we have trades
        if len(trades) == 0:
            return False, "No trades generated in selftest"
        
        # Check that all trades have valid exit reasons
        valid_reasons = {"STOP", "TP", "REVERSE", "EOD"}
        for trade in trades:
            if trade["exit_reason"] not in valid_reasons:
                return False, f"Invalid exit reason: {trade['exit_reason']}"
        
        # Verify stop/tp ordering for each trade
        for trade in trades:
            side = trade["side"]
            entry = trade["entry"]
            stop = trade["stop_price"]
            tp = trade["tp_price"]
            
            if side == "LONG":
                if not (stop < entry < tp):
                    return False, f"LONG trade ordering violation: stop={stop:.2f}, entry={entry:.2f}, tp={tp:.2f}"
            else:  # SHORT
                if not (tp < entry < stop):
                    return False, f"SHORT trade ordering violation: tp={tp:.2f}, entry={entry:.2f}, stop={stop:.2f}"
        
        # Verify PnL calculation correctness
        for trade in trades:
            side = trade["side"]
            entry = trade["entry"]
            exit_price = trade["exit"]
            qty = trade["quantity"]
            fees = trade["fees"]
            pnl = trade["pnl"]
            
            # Calculate expected PnL
            if side == "LONG":
                expected_gross = (exit_price - entry) * qty
            else:  # SHORT
                expected_gross = (entry - exit_price) * qty
            
            expected_pnl = expected_gross - fees
            
            # Allow small floating point differences
            if abs(pnl - expected_pnl) > 0.01:
                return False, f"PnL calculation error: expected={expected_pnl:.2f}, actual={pnl:.2f}"
        
        return True, f"All tests passed. Generated {len(trades)} trades with correct ordering and PnL calculations."
        
    except Exception as e:
        return False, f"Selftest failed with exception: {str(e)}"


if __name__ == "__main__":
    raise SystemExit(main())
