import pytest
import asyncio
from unittest.mock import MagicMock, patch
from laptop_agents.session.async_session import AsyncRunner
from laptop_agents.data.providers.mock import MockProvider

@pytest.mark.asyncio
async def test_session_lifecycle_initialization_to_shutdown(local_tmp_path):
    """Verify session can start, initialize tasks, and shut down gracefully."""
    strat_cfg = {
        "source": "mock",
        "setups": {
            "pullback_ribbon": {"enabled": False, "entry_band_pct": 0.001, "stop_atr_mult": 2.0, "tp_r_mult": 1.5},
            "sweep_invalidation": {"enabled": False}
        },
        "derivatives_gates": {"no_trade_funding_8h": 0.0005, "half_size_funding_8h": 0.0003, "extreme_funding_8h": 0.001},
        "risk": {"equity": 10000, "risk_pct": 0.01, "rr_min": 1.5}
    }
    
    # Patch seed_historical_candles to avoid waiting for history
    with patch("laptop_agents.session.lifecycle.seed_historical_candles", new_callable=MagicMock) as mock_seed:
        mock_seed.return_value = asyncio.Future()
        mock_seed.return_value.set_result(None)
        
        runner = AsyncRunner(
            symbol="BTCUSDT",
            interval="1m",
            strategy_config=strat_cfg,
            state_dir=local_tmp_path,
            provider=MockProvider(),
            execution_mode="paper"
        )
        
        from laptop_agents.session.lifecycle import run_session_lifecycle, request_shutdown
        
        # Run lifecycle as a task
        lifecycle_task = asyncio.create_task(run_session_lifecycle(runner, duration_min=1))
        
        # Wait for state to reach running
        for _ in range(10):
            if runner.status == "running":
                break
            await asyncio.sleep(0.1)
        
        assert runner.status == "running"
        
        # Trigger shutdown
        request_shutdown(runner, "test_shutdown")
        
        # Wait for task to finish
        await asyncio.wait_for(lifecycle_task, timeout=5.0)
        
        assert runner.shutdown_event.is_set()
        assert runner.stopped_reason == "test_shutdown"

@pytest.mark.asyncio
async def test_session_lifecycle_circuit_breaker_open(local_tmp_path):
    """Verify session shuts down immediately if circuit breaker is open."""
    strat_cfg = {
        "source": "mock",
        "risk": {"equity": 10000, "risk_pct": 0.01, "rr_min": 1.5},
        "setups": {"pullback_ribbon": {"enabled": False}, "sweep_invalidation": {"enabled": False}},
        "derivatives_gates": {"no_trade_funding_8h": 0.0005, "half_size_funding_8h": 0.0003, "extreme_funding_8h": 0.001}
    }
    
    runner = AsyncRunner(
        symbol="BTCUSDT",
        interval="1m",
        strategy_config=strat_cfg,
        state_dir=local_tmp_path,
        provider=MockProvider()
    )
    
    # Force trip circuit breaker
    for _ in range(10):
        runner.circuit_breaker.record_failure()
    
    assert not runner.circuit_breaker.allow_request()
    
    from laptop_agents.session.lifecycle import run_session_lifecycle
    
    with patch("laptop_agents.session.lifecycle.seed_historical_candles", new_callable=MagicMock) as mock_seed:
        mock_seed.return_value = asyncio.Future()
        mock_seed.return_value.set_result(None)
        
        await run_session_lifecycle(runner, duration_min=1)
        
        assert runner.shutdown_event.is_set()
        assert runner.stopped_reason == "circuit_breaker_open"
