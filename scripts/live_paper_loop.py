import argparse, json, time, os, sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# Add path for imports
sys.path.insert(0, 'src')

# Import resilience components
from laptop_agents.resilience.log import log_event
from laptop_agents.data.providers.bitunix_futures import BitunixFuturesProvider
from laptop_agents.resilience import (
    TransientProviderError,
    RateLimitProviderError,
    AuthProviderError,
    UnknownProviderError
)

# Import datetime for timestamp conversion
from datetime import datetime

def now_ms() -> int: return int(time.time()*1000)

@dataclass
class Candle:
    ts: int; o: float; h: float; l: float; c: float; v: float

def fetch_market_data(provider: BitunixFuturesProvider, symbol: str, interval: str, limit: int = 90) -> List[Candle]:
    """Fetch market data using resilient Bitunix provider."""
    try:
        # Use the existing resilience wrapper
        candles_data = provider.klines(interval=interval, limit=limit)
        
        # Convert to our Candle format
        out: List[Candle] = []
        for candle in candles_data:
            out.append(Candle(
                ts=int(datetime.fromisoformat(candle.ts).timestamp() * 1000),
                o=float(candle.open),
                h=float(candle.high),
                l=float(candle.low),
                c=float(candle.close),
                v=float(candle.volume)
            ))
        
        out.sort(key=lambda x: x.ts)
        return out
        
    except TransientProviderError as e:
        log_event("provider_error", {
            "exchange": "bitunix",
            "operation": "fetch_klines",
            "error_type": "TRANSIENT",
            "details": str(e),
            "severity": "medium"
        })
        raise
    except RateLimitProviderError as e:
        log_event("provider_error", {
            "exchange": "bitunix",
            "operation": "fetch_klines",
            "error_type": "RATE_LIMIT",
            "details": str(e),
            "severity": "low"
        })
        raise
    except AuthProviderError as e:
        log_event("provider_error", {
            "exchange": "bitunix",
            "operation": "fetch_klines",
            "error_type": "AUTH",
            "details": str(e),
            "severity": "high"
        })
        raise
    except UnknownProviderError as e:
        log_event("provider_error", {
            "exchange": "bitunix",
            "operation": "fetch_klines",
            "error_type": "UNKNOWN",
            "details": str(e),
            "severity": "high"
        })
        raise
    except Exception as e:
        log_event("provider_error", {
            "exchange": "bitunix",
            "operation": "fetch_klines",
            "error_type": "UNKNOWN",
            "details": str(e),
            "severity": "critical"
        })
        raise

def ema(vals: List[float], period: int) -> List[float]:
    if period <= 1: return vals[:]
    k = 2.0/(period+1.0)
    out=[]; e=None
    for v in vals:
        e = v if e is None else (v*k + e*(1.0-k))
        out.append(e)
    return out

def atr(candles: List[Candle], period: int) -> List[float]:
    if len(candles) < 2: return [0.0]*len(candles)
    trs=[0.0]
    for i in range(1,len(candles)):
        hi, lo, pc = candles[i].h, candles[i].l, candles[i-1].c
        trs.append(max(hi-lo, abs(hi-pc), abs(lo-pc)))
    return ema(trs, period)

def ms_per_interval(interval: str) -> int:
    unit = interval[-1]; n = int(interval[:-1])
    return n*60_000 if unit=="m" else n*3_600_000

def last_closed(candles: List[Candle], interval: str) -> Optional[Candle]:
    if len(candles) < 2: return None
    step = ms_per_interval(interval)
    last = candles[-1]
    return candles[-2] if now_ms() < (last.ts + step) else last

def safe_append_jsonl(path: str, obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    line = json.dumps(obj, separators=(",",":")) + "\n"
    for attempt in range(6):
        try:
            with open(path,"a",encoding="utf-8") as f:
                f.write(line)
            return
        except PermissionError:
            time.sleep(0.05*(attempt+1))
        except Exception:
            raise

def safe_save_state(path: str, st: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for attempt in range(6):
        tmp = f"{path}.tmp.{os.getpid()}"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(st, f, indent=2)
            try:
                os.replace(tmp, path)
                return
            finally:
                try: os.remove(tmp)
                except Exception: pass
        except PermissionError:
            time.sleep(0.05*(attempt+1))
        except Exception:
            break
    with open(path, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2)

def load_json(path: str, default: Any):
    try:
        with open(path,"r",encoding="utf-8") as f: return json.load(f)
    except Exception:
        return default

def normalize_paper_exit_event(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize legacy paper_exit events to ensure they have required fields.
    
    Returns None if event is invalid and should be ignored.
    Returns normalized event with all required fields.
    """
    try:
        # Skip if not a paper_exit event
        if event.get("event") != "paper_exit":
            return event
        
        # Check if event is already complete
        required_fields = ["exit", "pnl", "R", "reason"]
        if all(field in event for field in required_fields):
            return event
        
        # Try to upgrade legacy incomplete events
        if "exit" in event and "entry" in event and "side" in event:
            try:
                entry_price = float(event["entry"])
                exit_price = float(event["exit"])
                side = event["side"]
                
                # Calculate PnL (1 unit)
                if side == "LONG":
                    pnl = exit_price - entry_price
                else:  # SHORT
                    pnl = entry_price - exit_price
                
                # Calculate R (risk-adjusted return)
                # Use entry price as proxy for risk if we don't have stop/tp
                risk = entry_price * 0.01  # 1% of entry as proxy risk
                r_multiple = pnl / risk if risk > 0 else 0.0
                
                # Create upgraded event
                normalized = dict(event)
                normalized["pnl"] = pnl
                normalized["R"] = r_multiple
                normalized["reason"] = normalized.get("reason", "legacy_incomplete")
                
                return normalized
                
            except (ValueError, TypeError, ZeroDivisionError):
                # If we can't compute, mark as legacy_incomplete
                normalized = dict(event)
                normalized["reason"] = "legacy_incomplete"
                return normalized
        
        # Event is missing critical fields and can't be upgraded
        return None
        
    except Exception:
        # Never crash on bad data - just ignore the event
        return None

def load_journal_events(journal_path: str) -> List[Dict[str, Any]]:
    """Load and normalize journal events, filtering out invalid ones."""
    events = []
    if not os.path.exists(journal_path):
        return events
    
    try:
        with open(journal_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    normalized = normalize_paper_exit_event(event)
                    if normalized is not None:
                        events.append(normalized)
                except (json.JSONDecodeError, Exception):
                    # Skip invalid lines
                    continue
        return events
    except Exception:
        return []

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--interval", default="5m")
    ap.add_argument("--limit", type=int, default=90)
    ap.add_argument("--journal", default="data/paper_journal.jsonl")
    ap.add_argument("--state", default="data/paper_state.json")
    ap.add_argument("--control", default="data/control.json")
    ap.add_argument("--poll", type=int, default=60)
    ap.add_argument("--run-seconds", type=int, default=3600)  # 1h default; 0=forever
    ap.add_argument("--max-loops", type=int, default=0)  # 0=forever
    args = ap.parse_args()
    
    # Set up environment variables
    os.environ["RUN_ID"] = f"paper_{now_ms()}"
    os.environ["LOOP_SECONDS"] = str(args.poll)
    if args.max_loops > 0:
        os.environ["MAX_LOOPS"] = str(args.max_loops)
    
    # Initialize resilient Bitunix provider
    provider = BitunixFuturesProvider(symbol=args.symbol, allowed_symbols={args.symbol})
    
    # Log startup event
    log_event("loop_start", {
        "symbol": args.symbol,
        "interval": args.interval,
        "run_id": os.environ.get("RUN_ID"),
        "max_loops": args.max_loops,
        "run_seconds": args.run_seconds
    })

    st = load_json(args.state, {})
    st.setdefault("last_ts", 0)
    st.setdefault("position", None)
    st.setdefault("stats", {"trades":0,"wins":0,"losses":0,"sum_R":0.0})
    st.setdefault("loop_count", 0)
    st["symbol"]=args.symbol; st["interval"]=args.interval
    st["started_ms"] = now_ms()
    st["run_deadline_ms"] = int(now_ms() + args.run_seconds*1000) if (args.run_seconds and args.run_seconds>0) else 0

    os.makedirs(os.path.dirname(args.control), exist_ok=True)
    if not os.path.exists(args.control):
        with open(args.control,"w",encoding="utf-8") as f:
            json.dump({"paused": False, "extend_by_sec": 0}, f, indent=2)

    def j(event: str, **kw: Any):
        obj={"ts":now_ms(),"event":event,"symbol":args.symbol,"interval":args.interval,"source":"bitunix"}
        obj.update(kw)
        try:
            safe_append_jsonl(args.journal, obj)
        except Exception as ex:
            print(f"[journal_write_failed] {ex}", file=sys.stderr, flush=True)

    print("live_paper_loop starting…", flush=True)
    j("startup", msg="live_paper_loop started (hardened)")
    safe_save_state(args.state, st)

    warmup = 60
    last_hb = 0

    # Track loop count for max_loops support
    loop_count = 0
    
    while True:
        # Check max loops constraint
        if args.max_loops > 0 and loop_count >= args.max_loops:
            j("shutdown", reason="max_loops_reached")
            log_event("loop_shutdown", {
                "reason": "max_loops_reached",
                "completed_loops": loop_count,
                "max_loops": args.max_loops
            })
            safe_save_state(args.state, st)
            print(f"max loops ({args.max_loops}) reached; exiting", flush=True)
            break
            
        loop_count += 1
        st["loop_count"] = loop_count

        ctrl = load_json(args.control, {"paused": False, "extend_by_sec": 0})
        ext = int(ctrl.get("extend_by_sec", 0) or 0)
        if ext > 0 and st.get("run_deadline_ms", 0):
            st["run_deadline_ms"] = int(st["run_deadline_ms"]) + ext*1000
            ctrl["extend_by_sec"] = 0
            with open(args.control,"w",encoding="utf-8") as f: json.dump(ctrl, f, indent=2)
            j("extended", seconds=ext)

        st["paused"] = bool(ctrl.get("paused", False))
        dl = int(st.get("run_deadline_ms", 0) or 0)
        if dl and now_ms() >= dl:
            j("shutdown", reason="deadline reached")
            log_event("loop_shutdown", {
                "reason": "deadline_reached",
                "completed_loops": loop_count,
                "run_seconds": args.run_seconds
            })
            safe_save_state(args.state, st)
            print("deadline reached; exiting", flush=True)
            break

        if st["paused"]:
            if time.time() - last_hb >= 30:
                j("heartbeat", msg="paused")
                last_hb = time.time()
            safe_save_state(args.state, st)
            time.sleep(5)
            continue

        try:
            # Use resilient provider to fetch data
            candles = fetch_market_data(provider, args.symbol, args.interval, args.limit)
            lc = last_closed(candles, args.interval)
            
            if lc is None or len(candles) < warmup:
                if time.time() - last_hb >= 30:
                    j("heartbeat", msg="warming up", candles=len(candles))
                    log_event("loop_heartbeat", {
                        "status": "warming_up",
                        "candles_count": len(candles),
                        "warmup_required": warmup
                    })
                    last_hb = time.time()
                safe_save_state(args.state, st)
                time.sleep(args.poll)
                continue

            if int(lc.ts) <= int(st["last_ts"]):
                if time.time() - last_hb >= 30:
                    j("heartbeat", msg="no new closed candle yet", last_ts=st["last_ts"])
                    log_event("loop_heartbeat", {
                        "status": "waiting_for_new_candle",
                        "last_ts": st["last_ts"]
                    })
                    last_hb = time.time()
                safe_save_state(args.state, st)
                time.sleep(args.poll)
                continue

            st["last_ts"] = int(lc.ts)
            closes = [c.c for c in candles]
            e = ema(closes, 50)[-1]
            a = atr(candles, 14)[-1]
            
            # Log new candle event
            j("new_candle", candle_ts=int(lc.ts), close=float(closes[-1]), ema=float(e), atr=float(a))
            
            # Log to resilience events
            log_event("new_candle", {
                "candle_ts": int(lc.ts),
                "close": float(closes[-1]),
                "ema": float(e),
                "atr": float(a),
                "symbol": args.symbol,
                "interval": args.interval
            })
            
            # Paper trading logic
            try:
                current_close = float(closes[-1])
                
                # Check if we should open a position
                if st["position"] is None:
                    # Simple entry logic: breakout from EMA + ATR
                    entry_threshold = 0.2 * a
                    
                    if current_close > e + entry_threshold:
                        # Open LONG position
                        position = {
                            "side": "LONG",
                            "entry": current_close,
                            "entry_ts": int(lc.ts),
                            "stop": e,  # Stop at EMA
                            "tp": current_close + (1 * a)  # TP at 1x ATR
                        }
                        st["position"] = position
                        
                        j("paper_entry",
                          side="LONG",
                          entry=current_close,
                          entry_ts=int(lc.ts),
                          stop=position["stop"],
                          tp=position["tp"],
                          candle_ts=int(lc.ts))
                        
                        log_event("paper_entry", {
                            "side": "LONG",
                            "entry": current_close,
                            "entry_ts": int(lc.ts),
                            "stop": position["stop"],
                            "tp": position["tp"],
                            "candle_ts": int(lc.ts),
                            "reason": "breakout_above_ema"
                        })
                        
                        # Sync state after opening position
                        safe_save_state(args.state, st)
                        
                    elif current_close < e - entry_threshold:
                        # Open SHORT position
                        position = {
                            "side": "SHORT",
                            "entry": current_close,
                            "entry_ts": int(lc.ts),
                            "stop": e,  # Stop at EMA
                            "tp": current_close - (1 * a)  # TP at 1x ATR
                        }
                        st["position"] = position
                        
                        j("paper_entry",
                          side="SHORT",
                          entry=current_close,
                          entry_ts=int(lc.ts),
                          stop=position["stop"],
                          tp=position["tp"],
                          candle_ts=int(lc.ts))
                        
                        log_event("paper_entry", {
                            "side": "SHORT",
                            "entry": current_close,
                            "entry_ts": int(lc.ts),
                            "stop": position["stop"],
                            "tp": position["tp"],
                            "candle_ts": int(lc.ts),
                            "reason": "breakout_below_ema"
                        })
                        
                        # Sync state after opening position
                        safe_save_state(args.state, st)
                
                # Check if we should close an existing position
                elif st["position"] is not None:
                    position = st["position"]
                    
                    # Validate position data
                    if not isinstance(position, dict) or "side" not in position:
                        j("error", error="Invalid position data", context="paper_trading")
                        log_event("paper_trading_error", {
                            "error": "Invalid position data - clearing position",
                            "severity": "high",
                            "context": "position_validation"
                        })
                        st["position"] = None
                        safe_save_state(args.state, st)
                        continue
                    
                    exit_reason = None
                    exit_price = current_close
                    
                    if position["side"] == "LONG":
                        if current_close <= position["stop"]:
                            exit_reason = "stop_loss"
                        elif current_close >= position["tp"]:
                            exit_reason = "take_profit"
                    
                    elif position["side"] == "SHORT":
                        if current_close >= position["stop"]:
                            exit_reason = "stop_loss"
                        elif current_close <= position["tp"]:
                            exit_reason = "take_profit"
                    
                    if exit_reason:
                        # Calculate PnL and R
                        if position["side"] == "LONG":
                            pnl = (exit_price - position["entry"]) * 1.0  # 1 unit
                            risk = position["entry"] - position["stop"]
                        else:  # SHORT
                            pnl = (position["entry"] - exit_price) * 1.0  # 1 unit
                            risk = position["stop"] - position["entry"]
                        
                        r_multiple = pnl / risk if risk > 0 else 0.0
                        
                        # Update stats
                        st["stats"]["trades"] = st["stats"].get("trades", 0) + 1
                        if pnl > 0:
                            st["stats"]["wins"] = st["stats"].get("wins", 0) + 1
                        else:
                            st["stats"]["losses"] = st["stats"].get("losses", 0) + 1
                        st["stats"]["sum_R"] = st["stats"].get("sum_R", 0.0) + r_multiple
                        
                        # Log exit event
                        j("paper_exit",
                          side=position["side"],
                          entry=position["entry"],
                          exit=exit_price,
                          pnl=pnl,
                          R=r_multiple,
                          reason=exit_reason,
                          candle_ts=int(lc.ts))
                        
                        log_event("paper_exit", {
                            "side": position["side"],
                            "entry": position["entry"],
                            "exit": exit_price,
                            "pnl": pnl,
                            "R": r_multiple,
                            "reason": exit_reason,
                            "candle_ts": int(lc.ts),
                            "trades": st["stats"]["trades"],
                            "wins": st["stats"]["wins"],
                            "losses": st["stats"]["losses"],
                            "sum_R": st["stats"]["sum_R"]
                        })
                        
                        # Close position
                        st["position"] = None
                        
                        # Sync state after closing position
                        safe_save_state(args.state, st)
            
            except Exception as trade_ex:
                j("error", error=str(trade_ex), context="paper_trading")
                log_event("paper_trading_error", {
                    "error": str(trade_ex),
                    "severity": "medium",
                    "context": "trade_logic"
                })
                # Continue execution even if trading logic fails
            
            safe_save_state(args.state, st)
            time.sleep(args.poll)

        except (TransientProviderError, RateLimitProviderError, AuthProviderError, UnknownProviderError) as ex:
            # Provider-specific errors - log and continue
            error_type = type(ex).__name__.replace("ProviderError", "")
            j("error", error=str(ex), error_type=error_type, severity="medium")
            
            log_event("loop_error", {
                "error_type": error_type,
                "error_message": str(ex),
                "severity": "medium",
                "action": "retry_after_delay"
            })
            
            print(f"[provider_error/{error_type}] {ex}", file=sys.stderr, flush=True)
            safe_save_state(args.state, st)
            time.sleep(max(5, args.poll))
            
        except Exception as ex:
            # Generic errors - log and continue
            j("error", error=str(ex), error_type="UNKNOWN", severity="high")
            
            log_event("loop_error", {
                "error_type": "UNKNOWN",
                "error_message": str(ex),
                "severity": "high",
                "action": "retry_after_delay"
            })
            
            print(f"[loop_error] {ex}", file=sys.stderr, flush=True)
            safe_save_state(args.state, st)
            time.sleep(max(5, args.poll))

if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        print(f"[fatal] {ex}", file=sys.stderr, flush=True)
        raise
