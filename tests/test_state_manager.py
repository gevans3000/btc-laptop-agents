from laptop_agents.core.state_manager import StateManager


def test_state_persistence(local_tmp_path):
    sm = StateManager(local_tmp_path)
    sm.set("test_key", {"value": 123})
    sm.save()

    # Simulate restart
    sm2 = StateManager(local_tmp_path)
    assert sm2.get("test_key") == {"value": 123}


def test_circuit_breaker_state(local_tmp_path):
    sm = StateManager(local_tmp_path)
    sm.set_circuit_breaker_state({"tripped": False, "consecutive_losses": 2})
    sm.save()

    sm2 = StateManager(local_tmp_path)
    state = sm2.get_circuit_breaker_state()
    assert state["consecutive_losses"] == 2
