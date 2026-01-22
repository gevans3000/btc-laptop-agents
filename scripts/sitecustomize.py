import os
import pathlib
import tempfile


def safe_mkdtemp(suffix=None, prefix=None, dir=None):
    base = dir or tempfile.gettempdir()
    prefix = prefix or "tmp"
    suffix = suffix or ""
    while True:
        name = f"{prefix}{os.getpid()}-{os.urandom(6).hex()}{suffix}"
        path = pathlib.Path(base) / name
        try:
            path.mkdir(parents=True, exist_ok=False)
            return str(path)
        except FileExistsError:
            continue


tempfile.mkdtemp = safe_mkdtemp
