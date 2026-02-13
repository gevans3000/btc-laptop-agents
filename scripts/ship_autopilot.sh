#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash scripts/ship_autopilot.sh [branch]
# Example:
#   bash scripts/ship_autopilot.sh work

BRANCH="${1:-$(git rev-parse --abbrev-ref HEAD)}"

cd "$(git rev-parse --show-toplevel)"

echo "[1/7] Checkout branch: ${BRANCH}"
git checkout "${BRANCH}"

echo "[2/7] Update branch"
git pull --rebase

echo "[3/7] Install deps"
python -m pip install -e .[test]

echo "[4/7] Run unattended autopilot"
python scripts/parallel_alert_build.py --run-codex --merge --retries 3 --retry-delay-s 8 --merge-strategy theirs

echo "[5/7] Verify DONE marker"
test -f .codex_parallel/DONE

echo "[6/7] Push branch"
git push origin "${BRANCH}"

echo "[7/7] Optional PR creation with gh"
if command -v gh >/dev/null 2>&1; then
  gh pr create \
    --fill \
    --title "chore: unattended codex autopilot update" \
    --body "Automated autopilot run completed with completion report in .codex_parallel/completion_report.json" \
    || true
else
  echo "gh not installed; skipping PR creation"
fi

echo "DONE: updates applied, pushed, and PR attempted."
