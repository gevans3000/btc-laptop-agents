# Terminal Recovery + ZIP Build Steps (Ubuntu)

Use this file when your terminal shows `>` and commands get mixed.

## 1) Exit stuck `>` prompt

Press:

- `Ctrl + C`

You should return to a normal prompt like:

- `superg@nitro5:~$`

---

## 2) Run commands one-by-one (exact)

```bash
cd /home/superg/btc-laptop-agents
```

```bash
pwd
```

```bash
ls -lah docs/UBUNTU_AUTOPILOT_RUNBOOK.md docs/BTC_ALERT_PARALLEL_AUTOPILOT.md scripts/parallel_alert_build.py scripts/ship_autopilot.sh
```

If any file is missing, stop and fix branch/repo sync first.

```bash
mkdir -p dist
```

```bash
zip -r dist/ubuntu-autopilot-pack.zip docs/UBUNTU_AUTOPILOT_RUNBOOK.md docs/BTC_ALERT_PARALLEL_AUTOPILOT.md scripts/parallel_alert_build.py scripts/ship_autopilot.sh Makefile
```

```bash
ls -lah dist/ubuntu-autopilot-pack.zip
```

```bash
cp dist/ubuntu-autopilot-pack.zip ~/Desktop/
```

```bash
ls -lah ~/Desktop/ubuntu-autopilot-pack.zip
```

---

## 3) Why `>` appears

`>` usually means Bash is waiting for unfinished input, such as:

- unclosed quote (`"` or `'`)
- unclosed heredoc block (`cat <<'EOF'` not finished)
- accidental multiline paste truncation

Fix is always: `Ctrl + C`, then rerun commands line-by-line.

---

## 4) Final success checks

All must pass:

```bash
pwd
```

```bash
ls -lah dist/ubuntu-autopilot-pack.zip
```

```bash
ls -lah ~/Desktop/ubuntu-autopilot-pack.zip
```
