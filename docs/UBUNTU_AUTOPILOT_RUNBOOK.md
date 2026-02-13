# Ubuntu End-to-End Autopilot Runbook (BTC Laptop Agents)

This runbook is for **Ubuntu (latest)** and is designed for a developer to finish with minimal decision-making.

> Important truth: no one can guarantee 100% in advance because this flow depends on external tools/services (`codex`, git remote, optional `gh`, network). What we can guarantee is a reproducible process with machine-checkable success markers.

## Success criteria (must all be true)

1. `.codex_parallel/DONE` exists.
2. `.codex_parallel/completion_report.json` exists.
3. `git push` completes.
4. Optional: PR exists if `gh` is installed/authenticated.

---

## 1) One-time Ubuntu setup

```bash
sudo apt update
sudo apt install -y git make python3 python3-pip python3-venv curl zip
```

Install Codex CLI using your org method, then verify:

```bash
codex --version
```

Optional PR automation:

```bash
sudo apt install -y gh
gh --version
gh auth login
```

---

## 2) Clone / open repo

If not cloned yet:

```bash
cd ~
git clone <YOUR_REPO_URL> btc-laptop-agents
cd btc-laptop-agents
```

If already cloned:

```bash
cd ~/btc-laptop-agents
git fetch --all --prune
```

---

## 3) Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
```

---

## 4) Branch and dependencies

```bash
git checkout work || git checkout -b work
git pull --rebase || true
python -m pip install -e .[test]
```

---

## 5) Fully unattended run (single command)

```bash
bash scripts/ship_autopilot.sh work
```

This script will:
1. checkout/pull branch,
2. install deps,
3. run parallel codex tasks with retries,
4. merge branches,
5. verify `DONE` marker,
6. push branch,
7. attempt PR creation with `gh`.

---

## 6) Verify done state

```bash
ls -la .codex_parallel
cat .codex_parallel/completion_report.json
git status
git log --oneline -n 20
```

Expected:
- `DONE` file present,
- completion report exists,
- clean or expected git status,
- merge commits for agent branches.

---

## 7) Recovery (if any failure)

### Task failures

```bash
cat .codex_parallel/FAILED
cat .codex_parallel/*/codex_run.log | tail -n 200
bash scripts/ship_autopilot.sh work
```

### Merge failures

```bash
cat .codex_parallel/merge_conflicts.txt
git status
# resolve conflicts
git add <resolved_files>
git commit -m "resolve autopilot merge conflict"
bash scripts/ship_autopilot.sh work
```

### Missing codex

```bash
codex --version
# fix codex install/path
bash scripts/ship_autopilot.sh work
```

---

## 8) Zero-thinking command block (copy/paste)

```bash
cd ~/btc-laptop-agents
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
git checkout work || git checkout -b work
git pull --rebase || true
python -m pip install -e .[test]
bash scripts/ship_autopilot.sh work
ls -la .codex_parallel
```

---

## 9) Package this runbook + automation scripts into a zip

```bash
mkdir -p dist
zip -r dist/ubuntu-autopilot-pack.zip \
  docs/UBUNTU_AUTOPILOT_RUNBOOK.md \
  docs/BTC_ALERT_PARALLEL_AUTOPILOT.md \
  scripts/parallel_alert_build.py \
  scripts/ship_autopilot.sh \
  Makefile
```

Zip output path:

- `dist/ubuntu-autopilot-pack.zip`

You can move/copy that zip anywhere (Google Drive, Dropbox, external disk) for persistence.
