# BTC Alert Parallel Autopilot (Zero-Manual Workflow)

This workflow is for people who do **not** want to manually inspect each Codex task.

## Fastest path (Mac Mini / Linux)

```bash
cd /path/to/btc-laptop-agents
bash scripts/ship_autopilot.sh work
```

That command will:
1. checkout and update your branch,
2. install dependencies,
3. run all parallel codex tasks with retries,
4. merge task branches,
5. write completion artifacts,
6. push branch,
7. optionally create PR if `gh` exists.

## Completion artifacts (machine-checkable)

- `.codex_parallel/DONE` => all tasks succeeded.
- `.codex_parallel/FAILED` => one or more tasks failed.
- `.codex_parallel/completion_report.json` => detailed task status + commits + merge result.
- `.codex_parallel/status.json` => same status snapshot for external scripts.

## Commands-only run modes

### 1) First run (fully unattended)

```bash
python scripts/parallel_alert_build.py --run-codex --merge --retries 3 --retry-delay-s 8 --merge-strategy theirs
```

### 2) Resume after interruption

```bash
python scripts/parallel_alert_build.py --run-codex --merge --retries 3 --retry-delay-s 8 --merge-strategy theirs
```

### 3) A-D only (skip integration agent)

```bash
python scripts/parallel_alert_build.py --run-codex --merge --skip-merge-agent --retries 3 --retry-delay-s 8 --merge-strategy theirs
```

## Failure behavior

- Per-task logs are written to `.codex_parallel/<task>/codex_run.log`.
- Failed tasks are listed in `.codex_parallel/FAILED`.
- Merge errors write `.codex_parallel/merge_conflicts.txt`.
- Safe rerun: run the same command again; existing worktrees are reused.

## Notes

- Requires `codex` on PATH for `--run-codex` mode.
- `--merge-strategy theirs` is used for maximum unattended operation.
- `scripts/ship_autopilot.sh` attempts `gh pr create` if GitHub CLI is installed.
