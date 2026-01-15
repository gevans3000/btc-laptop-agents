"""Tests for TradingCircuitBreaker."""
import pytest
from laptop_agents.resilience.trading_circuit_breaker import TradingCircuitBreaker

def test_circuit_breaker_trips_on_consecutive_losses():
    cb = TradingCircuitBreaker(max_daily_drawdown_pct=10.0, max_consecutive_losses=5)
    cb.set_starting_equity(10000.0)
    
    # 5 consecutive losses should trip
    for i in range(5):
        cb.update_equity(10000 - (i+1)*100, trade_pnl=-100)
    
    assert cb.is_tripped(), "Circuit breaker should trip after 5 consecutive losses"

def test_circuit_breaker_trips_on_drawdown():
    cb = TradingCircuitBreaker(max_daily_drawdown_pct=5.0, max_consecutive_losses=10)
    cb.set_starting_equity(10000.0)
    
    # 6% drawdown should trip
    cb.update_equity(9400, trade_pnl=-600)
    
    assert cb.is_tripped(), "Circuit breaker should trip on 6% drawdown"

def test_circuit_breaker_resets_on_win():
    cb = TradingCircuitBreaker(max_daily_drawdown_pct=10.0, max_consecutive_losses=5)
    cb.set_starting_equity(10000.0)
    
    # 4 losses then 1 win
    for i in range(4):
        cb.update_equity(10000 - (i+1)*100, trade_pnl=-100)
    cb.update_equity(9800, trade_pnl=200)  # Win resets streak
    
    assert not cb.is_tripped(), "Circuit breaker should not trip after win resets streak"
