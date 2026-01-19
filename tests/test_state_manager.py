import tempfile
from pathlib import Path
from laptop_agents.core.state_manager import StateManager


def test_state_persistence():
    with tempfile.TemporaryDirectory() as td:
        sm = StateManager(Path(td))
        sm.set("test_key", {"value": 123})
        sm.save()

        # Simulate restart
        sm2 = StateManager(Path(td))
        assert sm2.get("test_key") == {"value": 123}


def test_circuit_breaker_state():
    with tempfile.TemporaryDirectory() as td:
        sm = StateManager(Path(td))
        sm.set_circuit_breaker_state({"tripped": False, "consecutive_losses": 2})
        sm.save()

        sm2 = StateManager(Path(td))
        state = sm2.get_circuit_breaker_state()
        assert state["consecutive_losses"] == 2
