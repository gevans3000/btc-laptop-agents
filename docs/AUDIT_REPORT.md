# Documentation & Operations Audit: BTC Laptop Agents

## 1. Repo Facts (Authoritative)

### Canonical Entrypoint
- **Authoritative Harness**: `python -m src.laptop_agents.run`
  - Used by all PowerShell MVP scripts.
  - Supports `--mode [live|backtest|selftest|orchestrated|validate|single]`.
- **Agent CLI (Modern)**: `la` (via `src/laptop_agents/cli.py`).
  - Implements `Supervisor` + `Agents` modular architecture.
  - **Note**: Currently disconnected from the main `/scripts/` lifecycle.

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
- **Trades**: `trades.csv` — Fixed columns: `trade_id, side, signal, entry, exit, quantity, pnl, fees, timestamp`.
- **Reports**: `summary.html` — Standalone dashboard.
- **State**: `paper/state.json` — Live position/balance tracking.

---

## 2. Docs Inventory & Drift Analysis

| File Path | Role | Status | Problems / Contradictions |
| :--- | :--- | :--- | :--- |
| `README.md` | Front Door | **STALE** | Misleading about Bitunix auth requirements (Public data is free). |
| `docs/MVP_SPEC.md` | The "Law" | **ACTIVE** | States `run_once` uses `mode=single`; script actually uses `mode=live`. |
| `docs/AGENTS.md` | Arch Guide | **CONFLICT** | Claims agents are "unwired"; `cli.py` clearly wires them to `la` command. |
| `docs/RUNBOOK.md` | Ops Manual | **ACTIVE** | Correct for `run.py` lifecycle; ignores `la` CLI entirely. |
| `docs/VERIFY.md` | QA Spec | **BLUEPRINT**| References `-Mode quick/full` which *are* implemented but not formally in `SPEC`. |

---

## 3. Contradiction Report (Ranked)

### [CRITICAL] Architectural Split
- **Evidence**: `AGENTS.md` (L5) says system is "MONOLITHIC". `cli.py` (L8) uses `Supervisor`.
- **Impact**: Agents may ignore the `agents/` directory logic when fixing bugs, leading to dead code or broken `la` CLI behavior while `run.py` stays stable.
- **Resolution**: Align `AGENTS.md` to acknowledge the dual-path reality: `run.py` is the MVP harness, `la` is the path to v1.1 modularity.

### [HIGH] `mvp_run_once.ps1` Behavioral Drift
- **Evidence**: `MVP_SPEC.md` (L71) vs `mvp_run_once.ps1` (L19).
- **Impact**: `run_once` creates a persistent `live` process state rather than an atomic simulation snapshot.
- **Resolution**: Synchronize script parameter to `--mode single` as intended by the spec.

### [MEDIUM] Data Source Obfuscation
- **Evidence**: `README.md` (L182-196).
- **Impact**: Users/Agents may waste time setting up `.env` for simple Bitunix candle testing.
- **Resolution**: Explicitly document that `--source bitunix` for candles is public/unauthenticated.

---

## 4. Proposed Documentation Set

I recommend adding/refactoring the following to achieve "Agent Readiness":

| File | Purpose | Location |
| :--- | :--- | :--- |
| **`docs/CONTRACT.md`** | Definition of Done (DoD) + Verification gates for Agents. | `docs/` |
| **`docs/SCHEMAS.md`** | Centralized Registry for all output formats (JSONL/CSV/JSON). | `docs/` |
| **`AGENT_GUIDE.md`** | Merged `AGENTS.md` + `DEV_AGENTS.md` + Handoff logic. | Root |

---

## 5. Ops Runbook (MVP Standards)

- **Start**: `.\scripts\mvp_start_live.ps1`
- **Stop**: `.\scripts\mvp_stop_live.ps1`
- **Status Check**: `.\scripts\mvp_status.ps1`
- **Health Check**: `.\scripts\verify.ps1 -Mode quick`
- **Visual Validation**: `.\scripts\mvp_open.ps1` (Checks `runs/latest/summary.html`).

---

## 6. Agent Workflow Blueprint

- **Rule 1**: Every task MUST begin with reading `docs/MVP_SPEC.md`.
- **Rule 2**: Every change MUST be verified with `.\scripts\verify.ps1`.
- **Rule 3**: If a change affects CLI flags or Output Schemas, the Agent **MUST** update `docs/MVP_SPEC.md` or `docs/SCHEMAS.md`.
- **Rule 4**: Use `assistant_sync_pack.md` (generated via script) to ground the session state before coding.

---

## 7. Next Steps (Actionable Checklist)

1. [ ] **Resolve SPEC Drift**: Update `MVP_SPEC.md` to reflect actual `mvp_run_once.ps1` usage of `--mode live`.
2. [ ] **Update Arch Guide**: Refactor `AGENTS.md` to document the existence of the `Supervisor` in `cli.py`.
3. [ ] **Consolidate AI Docs**: Merge `AGENTS.md` and `DEV_AGENTS.md` into a single `AGENT_GUIDE.md` in the root.
4. [ ] **Publicize Bitunix**: Add a "No-Key Bitunix Mode" section to `README.md`.
