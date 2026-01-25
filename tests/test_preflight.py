from laptop_agents.core.preflight import run_preflight, all_gates_passed
import os
from unittest.mock import patch


def test_run_preflight_success():
    results = run_preflight({})
    assert all_gates_passed(results)


def test_run_preflight_kill_switch():
    with patch.dict(os.environ, {"LA_KILL_SWITCH": "TRUE"}):
        results = run_preflight({})
        assert not all_gates_passed(results)
        kill_gate = next(r for r in results if r.name == "kill_switch_off")
        assert not kill_gate.passed
