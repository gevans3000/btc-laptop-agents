#!/usr/bin/env python3
"""Unattended orchestrator for parallel Codex tasks.

Features:
- Creates isolated worktrees/branches for each task.
- Runs Codex with retries per task.
- Auto-commits changes in each worktree branch.
- Merges branches back into target branch.
- Writes machine-readable completion/failure artifacts.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List


@dataclass(frozen=True)
class AgentTask:
    name: str
    branch: str
    commit_message: str
    prompt: str


TASKS: List[AgentTask] = [
    AgentTask(
        name="agent-a-data-budget",
        branch="agent/a-data-budget",
        commit_message="feat(alert): add ingestion budget manager and source fallback",
        prompt=(
            "Build data ingestion + global API budget manager for free-tier-safe usage. "
            "Implement per-provider per-minute/hour/day quota enforcement, cache fallback, "
            "and graceful degradation. Add tests for budget exhaustion behavior."
        ),
    ),
    AgentTask(
        name="agent-b-signal-engine",
        branch="agent/b-signal-engine",
        commit_message="feat(alert): implement signal stack and reason scorer",
        prompt=(
            "Implement technical signal engine using EMA/ATR/VWAP/CVD/sweep concepts and "
            "a deterministic reason scoring module that outputs confidence + top reasons. "
            "Add unit tests for scoring stability."
        ),
    ),
    AgentTask(
        name="agent-c-sentiment",
        branch="agent/c-sentiment-trump",
        commit_message="feat(alert): add sentiment aggregator and trump/policy keyword detector",
        prompt=(
            "Implement resilient sentiment aggregation from free sources and a Trump/policy "
            "headline keyword detector with dedup + confidence buckets. Add tests for keyword "
            "matching and dedup cache behavior."
        ),
    ),
    AgentTask(
        name="agent-d-telegram-ops",
        branch="agent/d-telegram-ops",
        commit_message="feat(alert): add telegram notifier with dedup and autopilot ops",
        prompt=(
            "Implement Telegram notifier pipeline with cooldown/dedup and automation scripts "
            "for run forever + health ping. Add smoke tests for dedup suppression logic."
        ),
    ),
    AgentTask(
        name="agent-e-merge-hardening",
        branch="agent/e-merge-hardening",
        commit_message="chore(alert): integrate modules with docs and integration checks",
        prompt=(
            "Integrate outputs of branches agent/a-data-budget, agent/b-signal-engine, "
            "agent/c-sentiment-trump, and agent/d-telegram-ops into a minimal alert-only "
            "repo structure. Ensure files stay under 500 lines, add concise README quickstart, "
            "and include an end-to-end dry-run test."
        ),
    ),
]


def run(cmd: Iterable[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(cmd), cwd=cwd, check=check, text=True, capture_output=True)


def ensure_git_repo() -> None:
    try:
        run(["git", "rev-parse", "--is-inside-work-tree"])
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"Not inside a git repository: {exc.stderr}")


def current_branch() -> str:
    return run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()


def tool_available(name: str) -> bool:
    probe = run(["bash", "-lc", f"command -v {name}"], check=False)
    return probe.returncode == 0


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_manifest(base_dir: Path, tasks: List[AgentTask]) -> None:
    write_json(
        base_dir / "manifest.json",
        {
            "tasks": [
                {
                    "name": t.name,
                    "branch": t.branch,
                    "commit_message": t.commit_message,
                    "prompt": t.prompt,
                }
                for t in tasks
            ]
        },
    )


def setup_worktrees(base_dir: Path, tasks: List[AgentTask], root: Path) -> None:
    for task in tasks:
        wt = base_dir / task.name
        if wt.exists() and (wt / ".git").exists():
            continue
        run(["git", "worktree", "add", "-b", task.branch, str(wt)], cwd=root)
        (wt / "TASK_PROMPT.txt").write_text(task.prompt + "\n", encoding="utf-8")


def invoke_codex_once(task: AgentTask, wt: Path) -> subprocess.CompletedProcess[str]:
    cmd = ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", task.prompt]
    return run(cmd, cwd=wt, check=False)


def invoke_codex_with_retries(task: AgentTask, wt: Path, retries: int, retry_delay_s: int) -> dict:
    attempts = 0
    while attempts <= retries:
        attempts += 1
        cp = invoke_codex_once(task, wt)
        log_path = wt / "codex_run.log"
        log_path.write_text((cp.stdout or "") + "\n" + (cp.stderr or ""), encoding="utf-8")
        if cp.returncode == 0:
            return {"ok": True, "attempts": attempts, "log": str(log_path)}
        if attempts <= retries:
            time.sleep(retry_delay_s * attempts)
    return {"ok": False, "attempts": attempts, "log": str(wt / "codex_run.log")}


def commit_if_needed(task: AgentTask, wt: Path) -> str | None:
    run(["git", "add", "-A"], cwd=wt)
    status = run(["git", "status", "--porcelain"], cwd=wt)
    if status.stdout.strip():
        run(["git", "commit", "-m", task.commit_message], cwd=wt)
        sha = run(["git", "rev-parse", "HEAD"], cwd=wt).stdout.strip()
        return sha
    return None


def merge_branches(tasks: List[AgentTask], root: Path, target_branch: str, strategy: str) -> None:
    run(["git", "checkout", target_branch], cwd=root)
    for task in tasks:
        cmd = ["git", "merge", "--no-ff", "-m", f"merge: {task.branch}"]
        if strategy == "ours":
            cmd += ["-X", "ours"]
        elif strategy == "theirs":
            cmd += ["-X", "theirs"]
        cmd.append(task.branch)
        run(cmd, cwd=root)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Unattended parallel Codex orchestrator")
    p.add_argument("--base-dir", default=".codex_parallel", help="Directory for worktrees and artifacts")
    p.add_argument("--prepare-only", action="store_true", help="Only create worktrees and prompts")
    p.add_argument("--run-codex", action="store_true", help="Run codex for each task")
    p.add_argument("--merge", action="store_true", help="Merge branches into current branch")
    p.add_argument("--skip-merge-agent", action="store_true", help="Skip running agent-e")
    p.add_argument("--retries", type=int, default=2, help="Retries per task when Codex fails")
    p.add_argument("--retry-delay-s", type=int, default=5, help="Base retry delay in seconds")
    p.add_argument("--merge-strategy", choices=["manual", "ours", "theirs"], default="manual")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    ensure_git_repo()
    root = Path.cwd()
    target = current_branch()
    base_dir = root / args.base_dir
    base_dir.mkdir(parents=True, exist_ok=True)

    done_marker = base_dir / "DONE"
    failed_marker = base_dir / "FAILED"
    if done_marker.exists():
        done_marker.unlink()
    if failed_marker.exists():
        failed_marker.unlink()

    selected_tasks = TASKS[:-1] if args.skip_merge_agent else TASKS
    write_manifest(base_dir, selected_tasks)
    setup_worktrees(base_dir, selected_tasks, root)

    if args.prepare_only and not args.run_codex and not args.merge:
        print(f"Prepared {len(selected_tasks)} worktrees at {base_dir}")
        return 0

    if args.run_codex and not tool_available("codex"):
        print("Codex CLI not found on PATH. Install/enable codex and rerun with --run-codex.")
        return 2

    status_rows = []
    failed_tasks = []
    for task in selected_tasks:
        wt = base_dir / task.name
        result = {"ok": True, "attempts": 0, "log": ""}
        if args.run_codex:
            result = invoke_codex_with_retries(task, wt, retries=args.retries, retry_delay_s=args.retry_delay_s)
        commit_sha = None
        if result["ok"]:
            commit_sha = commit_if_needed(task, wt)
            print(f"Completed: {task.name}")
        else:
            failed_tasks.append(task.name)
            print(f"Failed: {task.name} (see {result['log']})")
        status_rows.append(
            {
                "task": task.name,
                "branch": task.branch,
                "success": result["ok"],
                "attempts": result["attempts"],
                "log": result["log"],
                "commit": commit_sha,
            }
        )

    merged = False
    if args.merge and not failed_tasks:
        try:
            merge_branches(selected_tasks, root, target, strategy=args.merge_strategy)
            merged = True
            print(f"Merged {len(selected_tasks)} branches into {target}")
        except subprocess.CalledProcessError as exc:
            failed_tasks.append("merge")
            (base_dir / "merge_conflicts.txt").write_text(exc.stderr or exc.stdout or "merge failed", encoding="utf-8")

    report = {
        "timestamp": int(time.time()),
        "target_branch": target,
        "merged": merged,
        "merge_strategy": args.merge_strategy,
        "tasks": status_rows,
    }
    write_json(base_dir / "completion_report.json", report)
    write_json(base_dir / "status.json", report)

    if failed_tasks:
        failed_marker.write_text("\n".join(failed_tasks) + "\n", encoding="utf-8")
        print(f"FAILED tasks: {', '.join(failed_tasks)}")
        return 1

    done_marker.write_text("ok\n", encoding="utf-8")
    print("All tasks succeeded. DONE marker written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
