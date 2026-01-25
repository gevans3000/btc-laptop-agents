import subprocess
import sys
import os


def run_cmd(cmd, env=None, capture=False):
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, env=env, text=True, capture_output=capture)
    if result.returncode != 0:
        if capture:
            print(result.stdout)
            print(result.stderr)
        sys.exit(result.returncode)
    return result


def main():
    # 0. Formatting
    run_cmd("python -m ruff format src tests")
    run_cmd("python -m ruff check src tests --fix --extend-ignore=E402")

    # 1. Syntax & Analysis
    run_cmd("python -m compileall src scripts -q")
    run_cmd("python -m laptop_agents doctor --fix")

    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    run_cmd("python -m mypy src/laptop_agents --ignore-missing-imports", env=env)
    run_cmd(
        "python -m mypy src/laptop_agents/core --strict --ignore-missing-imports",
        env=env,
    )
    # run_cmd("python -m pip_audit")

    # 2. Tests
    # Note: Using coverage run for more reliable calculation.
    run_cmd("python -m coverage run --source=src -m pytest tests/ -q --tb=short")
    run_cmd("python -m coverage report")

    # 3. Build
    run_cmd("python -m build")

    # 4. Smoke Test
    run_cmd(
        "python -m laptop_agents run --mode live-session --duration 1 --source mock --dry-run"
    )

    # 5. Cleanup temp files before git operations to avoid pre-commit blocks
    for p in [
        "temp_go.ps1",
        "coverage_report.txt",
        "miss_report.txt",
        "cov_report.txt",
    ]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except:
                pass

    # 6. Git
    # Check for changes
    res = subprocess.run(
        "git diff --name-only --cached", shell=True, text=True, capture_output=True
    )
    staged = res.stdout.strip()
    if not staged:
        run_cmd("git add .")
        res = subprocess.run(
            "git diff --name-only --cached", shell=True, text=True, capture_output=True
        )
        staged = res.stdout.strip()

    if not staged:
        print("No changes to commit.")
        return

    # Commit
    scope = ""
    if "docs/" in staged:
        scope = "docs"
    elif "config/" in staged:
        scope = "config"
    elif "tests/" in staged:
        scope = "tests"
    elif "src/laptop_agents/core" in staged:
        scope = "core"
    elif "src/laptop_agents/agents" in staged:
        scope = "agents"
    elif "src/laptop_agents/data" in staged:
        scope = "data"
    elif "src/laptop_agents/paper" in staged:
        scope = "paper"
    elif "src/laptop_agents/execution" in staged:
        scope = "execution"
    elif "src/laptop_agents/strategy" in staged:
        scope = "strategy"
    elif "src/laptop_agents/backtest" in staged:
        scope = "backtest"
    elif "src/laptop_agents/session" in staged:
        scope = "session"
    elif "src/laptop_agents/resilience" in staged:
        scope = "resilience"
    elif "src/laptop_agents/commands" in staged:
        scope = "cli"
    elif "src/laptop_agents/reporting" in staged:
        scope = "reporting"
    elif "src/laptop_agents/dashboard" in staged:
        scope = "dashboard"
    elif "workflow" in staged:
        scope = "workflow"

    commit_type = "feat"
    if scope in ["docs"]:
        commit_type = "docs"
    if scope in ["config", "workflow"]:
        commit_type = "chore"
    if scope in ["tests"]:
        commit_type = "test"

    msg = (
        f"{commit_type}({scope}): auto-commit via /go"
        if scope
        else f"{commit_type}: auto-commit via /go"
    )

    # Try commit with retry for pre-commit fixes
    print(f"Committing changes: {msg}")
    result = subprocess.run(
        f'git commit -m "{msg}"', shell=True, text=True, capture_output=True
    )
    if result.returncode != 0:
        print("Commit failed (possibly pre-commit modified files). Retrying...")
        print(result.stdout)
        print(result.stderr)
        run_cmd("git add .")
        run_cmd(f'git commit -m "{msg}"')

    # Push
    run_cmd("git push origin main")

    print("\n=== DEPLOYMENT COMPLETE ===")
    run_cmd("git log -1 --oneline")


if __name__ == "__main__":
    main()
