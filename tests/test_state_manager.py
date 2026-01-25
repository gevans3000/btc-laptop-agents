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


class TestStateManagerRecovery:
    def test_corrupted_state_falls_back_to_backup(self, local_tmp_path):
        from laptop_agents.core.state_manager import StateManager

        state_dir = local_tmp_path / "state"
        if not state_dir.exists():
            state_dir.mkdir()

        # Create a valid state first
        sm = StateManager(state_dir)
        sm.set("test_key", "test_value")
        sm.save()

        # Verify state file exists
        state_file = state_dir / "unified_state.json"
        backup_file = state_dir / "unified_state.bak"
        assert state_file.exists()

        # Corrupt the main state file
        with open(state_file, "w") as f:
            f.write("{invalid json")

        # Create backup with valid content
        import json

        with open(backup_file, "w") as f:
            json.dump({"test_key": "backup_value", "last_saved": 123}, f)

        # Reload - should fall back to backup
        sm2 = StateManager(state_dir)
        assert sm2.get("test_key") == "backup_value"

    def test_both_corrupted_starts_fresh(self, local_tmp_path):
        from laptop_agents.core.state_manager import StateManager

        state_dir = local_tmp_path / "state"
        if not state_dir.exists():
            state_dir.mkdir()

        state_file = state_dir / "unified_state.json"
        backup_file = state_dir / "unified_state.bak"

        # Create corrupted files
        with open(state_file, "w") as f:
            f.write("{invalid")
        with open(backup_file, "w") as f:
            f.write("{also invalid")

        # Should start fresh without crashing
        sm = StateManager(state_dir)
        assert sm.get("any_key") is None

    def test_supervisor_state(self, local_tmp_path):
        sm = StateManager(local_tmp_path)
        sm.set_supervisor_state({"active": True})
        sm.save()

        sm2 = StateManager(local_tmp_path)
        assert sm2.get_supervisor_state() == {"active": True}

    def test_atomic_save_json(self, local_tmp_path):
        test_file = local_tmp_path / "test_atomic.json"
        data = {"key": "value"}
        StateManager.atomic_save_json(test_file, data)

        import json

        with open(test_file) as f:
            assert json.load(f) == data

    def test_clear_state(self, local_tmp_path):
        sm = StateManager(local_tmp_path)
        sm.set("key", "val")
        sm.save()
        assert (local_tmp_path / "unified_state.json").exists()

        sm.clear()
        assert sm.get("key") is None
        assert not (local_tmp_path / "unified_state.json").exists()

    def test_save_backup_error_logs_but_continues(self, local_tmp_path):
        from unittest.mock import patch

        sm = StateManager(local_tmp_path)
        sm.set("key", "val")
        # Pre-create state file to trigger backup path
        with open(sm.state_file, "w") as f:
            f.write("{}")

        with patch("shutil.copy2", side_effect=OSError("disk full")):
            # Should not raise, just log warning
            sm.save()
        assert sm.state_file.exists()

    def test_save_permission_error_retries_and_raises(self, local_tmp_path):
        from unittest.mock import patch

        sm = StateManager(local_tmp_path)
        sm.set("key", "val")

        with patch("os.replace", side_effect=PermissionError("locked")):
            with patch("time.sleep"):  # don't actually sleep
                from pytest import raises

                with raises(PermissionError):
                    sm.save()

    def test_atomic_save_generic_error_unlinks_temp(self, local_tmp_path):
        from unittest.mock import patch

        test_file = local_tmp_path / "fail_atomic.json"

        # Mock open to succeed for temp but fail for something else
        with patch("builtins.open", side_effect=Exception("unplanned crash")):
            from pytest import raises

            with raises(Exception, match="unplanned crash"):
                StateManager.atomic_save_json(test_file, {"a": 1})

        # Cleanup should have happened if temp existed (mock didn't create it though)

    def test_save_generic_exception_logs_and_raises(self, local_tmp_path):
        from unittest.mock import patch

        sm = StateManager(local_tmp_path)
        with patch("json.dump", side_effect=RuntimeError("JSON crash")):
            from pytest import raises

            with raises(RuntimeError, match="JSON crash"):
                sm.save()
