# Documentation & Operations Audit: BTC Laptop Agents

> **Phase**: D (Modularization & Stabilization) — COMPLETE  
> **Last Updated**: 2026-01-12

---

## 1. Repo Facts (Authoritative)

### Canonical Entrypoint
- **Primary Harness**: `python -m src.laptop_agents.run`
  - Used by all PowerShell MVP scripts.
  - Supports `--mode [live|backtest|selftest|orchestrated|validate|single]`.

### Architecture
The codebase has transitioned from monolith to modular design:

| Component | Location | Responsibility |
| :--- | :--- | :--- |
| CLI Wrapper | `src/laptop_agents/run.py` | Thin CLI (~101 lines) |
| Orchestrator | `src/laptop_agents/core/orchestrator.py` | Mode dispatch (modular + legacy) |
| Data Loader | `src/laptop_agents/data/loader.py` | Mock + Bitunix candle fetching |
| Exec Engine | `src/laptop_agents/trading/exec_engine.py` | Live paper trading loop |
| Signal | `src/laptop_agents/trading/signal.py` | ATR filter + SMA crossover |

### Modes & Defaults
- **Default Mode**: `single` (code default) / `live` (script default).
- **Default Source**: `mock` (Generates synthetic sine-wave data).
- **Canonical Scripts**:
  - `verify.ps1`: Health/Logic check.
  - `mvp_start_live.ps1` / `mvp_stop_live.ps1`: Daemon management.
  - `mvp_status.ps1`: Life-cycle check.
  - `mvp_run_once.ps1`: Single loop execution.

### Artifacts & Schemas
- **Events**: `events.jsonl` (JSONL) — Must contain `timestamp` and `event`.
- **Trades**: `trades.csv` — Columns: `trade_id, side, signal, entry, exit, quantity, pnl, fees, timestamp, exit_reason`.
- **Reports**: `summary.html` — Standalone dashboard.
- **State**: `paper/state.json` — Live position/balance tracking.

---

## 2. Docs Inventory & Status

| File Path | Role | Status | Notes |
| :--- | :--- | :--- | :--- |
| `README.md` | Front Door | ✓ ACTIVE | Accurate for MVP usage |
| `docs/SPEC.md` | The "Law" | ✓ ACTIVE | Authoritative source of truth |
| `docs/AGENTS.md` | Arch Guide | ✓ UPDATED | Modular pipeline documented |
| `docs/RUNBOOK.md` | Ops Manual | ✓ ACTIVE | Covers orchestrated + legacy modes |
| `docs/MAP.md` | Navigation | ✓ UPDATED | Accurate file/line references |
| `docs/AI_HANDOFF.md` | Agent Context | ✓ UPDATED | Sync pack references removed |
| `docs/DEV_AGENTS.md` | Dev Rules | ✓ ACTIVE | Modular awareness documented |
| `docs/NEXT.md` | Roadmap | ✓ UPDATED | Phase D marked complete |
| `docs/VERIFY.md` | QA Spec | ✓ ACTIVE | Matches verify.ps1 behavior |

---

## 3. Resolved Issues (Phase D)

### ✓ Code Cleanup
- `exec_engine.py` trailing duplicate code removed
- `run.py` reduced to thin wrapper

### ✓ Sync Pack Elimination
- `scripts/make_sync_pack.ps1` — DELETED
- `assistant_sync_pack.md` — DELETED

### ✓ Documentation Alignment
- All docs updated to reflect modular architecture
- MAP.md table formatting fixed
- Outdated file/line references corrected

---

## 4. Verification Results

| Check | Status |
| :--- | :--- |
| `python -m compileall src` | ✓ PASS |
| `verify.ps1 -Mode quick` | ✓ PASS |
| Selftest (conservative) | ✓ PASS |
| Selftest (optimistic) | ✓ PASS |
| Artifact validation | ✓ PASS |

---

## 5. Agent Workflow Blueprint

- **Rule 1**: Every task MUST begin with reading `docs/SPEC.md`.
- **Rule 2**: Every change MUST be verified with `.\scripts\verify.ps1`.
- **Rule 3**: If a change affects CLI flags or Output Schemas, update `docs/SPEC.md`.
- **Rule 4**: Check `docs/MAP.md` if modifying module locations.

---

## 6. Ops Runbook (MVP Standards)

| Action | Command |
| :--- | :--- |
| Start | `.\scripts\mvp_start_live.ps1` |
| Stop | `.\scripts\mvp_stop_live.ps1` |
| Status Check | `.\scripts\mvp_status.ps1` |
| Health Check | `.\scripts\verify.ps1 -Mode quick` |
| Visual Validation | `.\scripts\mvp_open.ps1` |

---

## 7. Summary

**The repository is CLEAN, MODULAR, and AGENT-READY.**

All Phase D objectives complete. The codebase is ready for the next phase of development.
