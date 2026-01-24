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
