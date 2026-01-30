import subprocess
import sys
from pathlib import Path

# Resolve REPO_ROOT: tests/ -> root
REPO_ROOT = Path(__file__).resolve().parent.parent


def run_command(cmd_args: list[str]) -> subprocess.CompletedProcess:
    """Run command from REPO_ROOT and return result."""
    import os

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    return subprocess.run(
        [sys.executable] + cmd_args,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


def cleanup_lock():
    """Force cleanup of lock file."""
    lock_file = REPO_ROOT / ".workspace" / "agent.pid"
    try:
        if lock_file.exists():
            lock_file.unlink()
    except Exception:
        pass


def test_selftest():
    cleanup_lock()
    print("1. Testing --mode selftest...")
    result = run_command(["-m", "laptop_agents", "run", "--mode", "selftest"])
    cleanup_lock()

    if result.returncode != 0:
        print("[FAIL] Selftest returned non-zero exit code.")
        print("STDERR:", result.stderr)
        assert result.returncode == 0, f"Selftest failed with stderr: {result.stderr}"

    full_output = result.stdout + result.stderr
    if "SELFTEST PASS" not in full_output:
        print("[FAIL] 'SELFTEST PASS' not found in output.")
        assert False, "'SELFTEST PASS' not found in output."

    print("[PASS] Selftest successful.")


def test_backtest_reproducibility():
    cleanup_lock()
    print("2. Testing --mode backtest artifacts...")

    # Run small backtest
    result = run_command(
        [
            "-m",
            "laptop_agents",
            "run",
            "--mode",
            "backtest",
            "--source",
            "mock",
            "--backtest",
            "100",
        ]
    )

    if result.returncode != 0:
        print("[FAIL] Backtest returned non-zero exit code.")
        print("STDERR:", result.stderr)
        assert result.returncode == 0, f"Backtest failed with stderr: {result.stderr}"

    runs_dir = REPO_ROOT / ".workspace" / "runs" / "latest"
    required = ["summary.html", "trades.csv", "events.jsonl"]

    for filename in required:
        file_path = runs_dir / filename
        if not file_path.exists():
            print(f"[FAIL] Missing artifact: {filename}")
            assert False, f"Missing artifact: {filename}"
        if file_path.stat().st_size == 0:
            print(f"[FAIL] Empty artifact: {filename}")
            assert False, f"Empty artifact: {filename}"

    print(f"[PASS] Artifacts generated in {runs_dir}")


if __name__ == "__main__":
    print(f"Running Reproducibility Tests from {REPO_ROOT}")
    test_selftest()
    test_backtest_reproducibility()
    print("ALL TESTS PASSED")
