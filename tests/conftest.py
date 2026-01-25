import os
from pathlib import Path

import pytest


def pytest_configure(config):
    base = Path(__file__).resolve().parents[1] / "local_pytest_temp"
    base.mkdir(parents=True, exist_ok=True)
    temp_path = str(base)
    os.environ["TMPDIR"] = temp_path
    os.environ["TEMP"] = temp_path
    os.environ["TMP"] = temp_path


@pytest.fixture
def local_tmp_path():
    import tempfile

    with tempfile.TemporaryDirectory(prefix="pytest_") as tmpdir:
        yield Path(tmpdir)


@pytest.fixture(autouse=True)
def clean_workspace_pid():
    """Remove stale PID file before each test to prevent 'Already running' errors."""
    from pathlib import Path

    pid_file = Path(__file__).resolve().parents[1] / ".workspace" / "agent.pid"
    if pid_file.exists():
        try:
            pid_file.unlink()
        except Exception:
            pass
    yield
    # Cleanup after test as well
    if pid_file.exists():
        try:
            pid_file.unlink()
        except Exception:
            pass
