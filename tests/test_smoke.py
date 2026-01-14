from laptop_agents.core.runner import Runner

def test_runner_smoke(tmp_path):
    r = Runner(data_dir=str(tmp_path))
    out = r.run("planner", "Create a checklist for backing up files")
    assert "PLAN for:" in out


def test_timed_session_mock():
    """Run a brief mock session, verify no crashes."""
    from laptop_agents.session.timed_session import run_timed_session
    
    # Run a very short session with mock data
    result = run_timed_session(
        duration_min=0.2,  # ~12 seconds
        poll_interval_sec=2,
        source="mock",
        symbol="BTCUSD",
        limit=200,
    )
    
    assert result.iterations >= 1, "Should complete at least 1 iteration"
    assert result.errors == 0, f"Should have no errors, got {result.errors}"
    assert result.stopped_reason == "completed", f"Should stop normally, got {result.stopped_reason}"
    assert result.starting_equity == 10000.0

