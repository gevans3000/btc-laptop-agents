import asyncio
import time
import psutil
import os
import sys
import shutil
from pathlib import Path
import pytest
from laptop_agents.session.async_session import AsyncRunner
from laptop_agents.trading.helpers import Candle, Tick

class MockFastProvider:
    def __init__(self, candles):
        self.candles = candles
        
    async def listen(self):
        for c in self.candles:
            yield c
            
    async def funding_rate(self):
        return 0.0001
    
    async def fetch_and_inject_gap(self, s, e):
        pass

@pytest.mark.asyncio
async def test_high_load_stress():
    """
    Stress test: Feed 10,000 candles into AsyncRunner at max speed.
    Ensures memory stability and zero internal errors under high throughput.
    """
    num_candles = 10000
    print(f"\n[STRESS TEST] Starting {num_candles} candle injection...")
    
    # 1. Setup Data
    candles = []
    for i in range(num_candles):
        candles.append(Candle(
            ts=str(1700000000 + i * 60),
            open=100.0 + (i % 10), 
            high=110.0 + (i % 10), 
            low=90.0 + (i % 10), 
            close=105.0 + (i % 10),
            volume=1000.0
        ))
    
    # 2. Setup Config (ensure all keys needed by agents exist)
    valid_config = {
        "engine": {
            "min_history_bars": 100, 
            "pending_trigger_max_bars": 24, 
            "derivatives_refresh_bars": 6
        },
        "setups": {
            "pullback_ribbon": {
                "enabled": True, 
                "entry_band_pct": 0.001, 
                "stop_atr_mult": 1.5, 
                "tp_r_mult": 2.0
            },
            "sweep_invalidation": {
                "enabled": False, 
                "lookback_bars": 10, 
                "min_vol_ratio": 0.5, 
                "stop_atr_mult": 0.5
            }
        },
        "derivatives_gates": {
            "enabled": True,
            "no_trade_funding_8h": 0.05,
            "half_size_funding_8h": 0.03,
            "extreme_funding_8h": 0.1
        },
        "risk": {
            "equity": 10000.0, 
            "risk_pct": 1.0, 
            "rr_min": 1.5
        },
        "cvd": {
            "enabled": False,
            "lookback": 20
        }
    }
    
    # Use unique state path to avoid WinError 32
    state_dir = Path("tests/stress/run_data")
    if state_dir.exists():
        shutil.rmtree(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    
    provider = MockFastProvider(candles)
    
    # Patch PAPER_DIR globally just for this test if needed, 
    # but AsyncRunner and PaperBroker take paths now.
    runner = AsyncRunner(
        symbol="BTCUSDT",
        interval="1m",
        starting_balance=10000.0,
        strategy_config=valid_config,
        provider=provider,
        state_dir=state_dir,
        dry_run=True
    )
    # Disable circuit breaker for stress testing throughput
    runner.circuit_breaker.max_daily_drawdown_pct = 100.0
    runner.circuit_breaker.max_consecutive_losses = 999
    
    # Ensure broker writes to our temp dir
    runner.broker.state_path = str(state_dir / "broker_state.json")
    
    start_time = time.time()
    
    count = 0
    for candle in candles:
        # Check if this is a NEW candle 
        if not runner.candles or candle.ts != runner.candles[-1].ts:
            if runner.candles:
                try:
                    await runner.on_candle_closed(runner.candles[-1])
                except Exception as e:
                    print(f"ERROR at candle {count}: {e}")
                    raise
            runner.candles.append(candle)
            if len(runner.candles) > 200:
                runner.candles = runner.candles[-200:]
            count += 1
        else:
            runner.candles[-1] = candle
            
    duration = time.time() - start_time
    process = psutil.Process(os.getpid())
    mem_mb = process.memory_info().rss / 1024 / 1024
    
    print(f"[STRESS TEST] Processed {count} candles in {duration:.2f}s")
    print(f"[STRESS TEST] Throughput: {count/duration:.1f} candles/sec")
    print(f"[STRESS TEST] Memory: {mem_mb:.2f} MB")
    print(f"[STRESS TEST] Errors: {runner.errors}")
    print(f"[STRESS TEST] Trades: {runner.trades}")
    
    # Verification
    if runner.errors > 0:
        print(f"FAILED: Expected 0 errors, got {runner.errors}")
        sys.exit(1)
    if count != num_candles:
        print(f"FAILED: Expected {num_candles} processed, got {count}")
        sys.exit(1)
    if mem_mb > 500:
        print(f"FAILED: Memory leak detected: {mem_mb:.2f} MB > 500 MB")
        sys.exit(1)
        
    print("[STRESS TEST] SUCCESS")
    
    # Final cleanup
    await asyncio.to_thread(runner.broker.shutdown)
    if state_dir.exists():
        try:
            shutil.rmtree(state_dir)
        except:
            pass

if __name__ == "__main__":
    try:
        asyncio.run(test_high_load_stress())
    except Exception as e:
        print(f"STRESS TEST UNCAUGHT ERROR: {e}")
        sys.exit(1)
