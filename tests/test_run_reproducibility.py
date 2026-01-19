import subprocess
import sys
from pathlib import Path

# Resolve REPO_ROOT: tests/ -> root
REPO_ROOT = Path(__file__).resolve().parent.parent


def run_command(cmd_args: list[str]) -> subprocess.CompletedProcess:
    """Run command from REPO_ROOT and return result."""
    return subprocess.run(
        [sys.executable] + cmd_args, cwd=REPO_ROOT, capture_output=True, text=True
    )


def test_selftest():
    print("1. Testing --mode selftest...")
    result = run_command(["-m", "laptop_agents", "run", "--mode", "selftest"])

    if result.returncode != 0:
        print("[FAIL] Selftest returned non-zero exit code.")
        print("STDERR:", result.stderr)
        sys.exit(1)

    full_output = result.stdout + result.stderr
    if "SELFTEST PASS" not in full_output:
        print("[FAIL] 'SELFTEST PASS' not found in output.")
        sys.exit(1)

    print("[PASS] Selftest successful.")


def test_backtest_reproducibility():
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
        sys.exit(1)

    runs_dir = REPO_ROOT / ".workspace" / "runs" / "latest"
    required = ["summary.html", "trades.csv", "events.jsonl"]

    for filename in required:
        file_path = runs_dir / filename
        if not file_path.exists():
            print(f"[FAIL] Missing artifact: {filename}")
            sys.exit(1)
        if file_path.stat().st_size == 0:
            print(f"[FAIL] Empty artifact: {filename}")
            sys.exit(1)

    print(f"[PASS] Artifacts generated in {runs_dir}")


if __name__ == "__main__":
    print(f"Running Reproducibility Tests from {REPO_ROOT}")
    test_selftest()
    test_backtest_reproducibility()
    print("ALL TESTS PASSED")
