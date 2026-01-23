"""Tests for ErrorCircuitBreaker (consolidated from TradingCircuitBreaker)."""

from laptop_agents.resilience import ErrorCircuitBreaker


def test_circuit_breaker_trips_on_failures():
    # Trips after 5 failures
    cb = ErrorCircuitBreaker(failure_threshold=5, time_window=60)

    # 4 failures should not trip
    for i in range(4):
        cb.record_failure()
        assert cb.allow_request()

    # 5th failure should trip
    cb.record_failure()
    assert not cb.allow_request(), "Circuit breaker should trip after 5 failures"


def test_circuit_breaker_resets_on_success():
    cb = ErrorCircuitBreaker(failure_threshold=5, time_window=60, recovery_timeout=0.1)

    # Trip the circuit
    for i in range(5):
        cb.record_failure()
    assert not cb.allow_request()

    # Wait for recovery
    import time

    time.sleep(0.2)

    # Should allow request now
    assert cb.allow_request()

    # Success should reset failures
    cb.record_success()
    assert cb.state == "CLOSED"
    assert len(cb.failures) == 0
