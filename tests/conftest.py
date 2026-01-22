import os
from pathlib import Path
import shutil
import uuid

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
    base = Path(__file__).resolve().parents[1] / "local_pytest_temp"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"run_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
