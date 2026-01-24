from unittest.mock import patch


def test_timed_session_mock():
    """Run a brief mock session, verify no crashes."""
    from laptop_agents.session.timed_session import run_timed_session

    # Mock time to avoid real sleep
    # We patch the time module inside the timed_session module

    start_ts = 1700000000.0  # Fixed start time

    # We use a mutable object to hold current time state
    time_state = {"now": start_ts}

    def mock_time():
        time_state["now"] += 0.001
        return time_state["now"]

    def mock_sleep(seconds):
        time_state["now"] += seconds

    with patch("laptop_agents.session.timed_session.time") as mock_time_mod:
        mock_time_mod.time.side_effect = mock_time
        mock_time_mod.sleep.side_effect = mock_sleep

        result = run_timed_session(
            duration_min=1,
            poll_interval_sec=2,
            source="mock",
            symbol="BTCUSDT",
            limit=200,
        )

        assert result.iterations >= 1, "Should complete at least 1 iteration"
        assert result.errors == 0, f"Should have no errors, got {result.errors}"
        assert result.stopped_reason in [
            "completed",
            "duration_limit_reached",
        ], f"Should stop normally, got {result.stopped_reason}"
        assert result.starting_equity == 10000.0
