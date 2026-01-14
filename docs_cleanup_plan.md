# Documentation Cleanup Implementation Plan

> **Status**: READY FOR EXECUTION  
> **Generated**: 2026-01-12  
> **Executor**: AI Agent (Deterministic)  
> **Estimated Effort**: 30-45 minutes

---

## 1. Assumptions

The following baseline truths govern all decisions in this plan:

| # | Assumption | Rationale |
|---|------------|-----------|
| 1 | The repo is moving toward a **modular orchestrated architecture** | Evidence: `docs/ORCHESTRATION.md`, `docs/PHASE_E_PLAN.md`, code in `src/laptop_agents/agents/` |
| 2 | **Python 3.10+** is the minimum supported version | Evidence: `pyproject.toml` line 9: `requires-python = ">=3.10"` |
| 3 | **Stricter safety limits** are preferred when conflicts exist | User heuristic instruction |
| 4 | The **code is the source of truth** for hard limits | `hard_limits.py`: `MIN_RR_RATIO=1.0`, `MAX_LEVERAGE=20.0`, `MAX_POSITION_SIZE_USD=200000` |
| 5 | **`docs/SPEC.md`** is the canonical documentation authority | Declared in SPEC.md line 6: "Single Source of Truth" |
| 6 | **`task.md`** indicates prior cleanup was performed on 2026-01-12 | Some issues may already be resolved or partially addressed |
| 7 | Files marked `SUPERSEDED` should be retained for history but clearly marked | Prevents confusion without losing context |
| 8 | **UTF-8 without BOM** is the encoding standard | Windows-compatible, GitHub-friendly |
| 9 | The `.agent/` directory contains internal tooling, not public docs | Excluded from public-facing cleanup |
| 10 | **No file renames** unless explicitly necessary | Minimizes link breakage and git history complexity |

---

## 2. Repository Discovery Strategy

### Files Analyzed

| Glob Pattern | Count | Location |
|--------------|-------|----------|
| `*.md` (root) | 2 | `README.md`, `task.md` |
| `docs/*.md` | 18 | Primary documentation |
| `.agent/**/*.md` | 6 | Agent-internal workflows and artifacts |

### Full File Inventory (26 Markdown Files)

```
README.md
task.md
docs/AGENTS.md
docs/AI_HANDOFF.md
docs/API_REFERENCE.md
docs/AUDIT_REPORT.md
docs/DEV_AGENTS.md
docs/GATES.md
docs/GIT_WORKFLOW.md
docs/KNOWN_ISSUES.md
docs/MAP.md
docs/NEXT.md
docs/ORCHESTRATION.md
docs/PHASE_E_PLAN.md
docs/QA_VALIDATION_PLAN.md
docs/RUNBOOK.md
docs/SPEC.md
docs/START_HERE.md
docs/TESTING.md
docs/VERIFY.md
.agent/instructions.md
.agent/DIRECTIVES.md
.agent/workflows/turbo_save.md
.agent/workflows/save-progress.md
.agent/workflows/merge-recovery.md
.agent/workflows/docs-cleanup.md
.agent/workflows/docs-cleanup-plan.md
.agent/artifacts/MARKDOWN_AUDIT_REPORT.md
```

---

## 3. Audit Methodology

### Categorization Approach

1. **Semantic Analysis**: Read each file to understand purpose and audience
2. **Cross-Reference Check**: Identify conflicting values across files
3. **Code Verification**: Compare documentation claims against actual source code
4. **Link Validation**: Check for references to non-existent files
5. **Encoding Inspection**: Detect garbled Unicode characters (UTF-8 issues)
6. **Status Header Audit**: Check for consistent status markers

### Conflict Resolution Heuristics

| Conflict Type | Resolution Rule |
|---------------|-----------------|
| Numeric limits | Code (`hard_limits.py`) wins; document as "Hard limit: X, Config default: Y" |
| Python version | `pyproject.toml` wins (3.10+) |
| Mode defaults | Code wins; document both code and script defaults explicitly |
| Missing files | Remove reference OR add "(Planned)" suffix |
| Duplicate content | Keep authoritative source, mark other as SUPERSEDED |

---

## 4. Issue Taxonomy & Severity

| ID | Issue | Severity | Files Affected | Resolution |
|----|-------|----------|----------------|------------|
| **C1** | `MIN_RR_RATIO` conflict: SPEC says 1.5R, code says 1.0R | P0 Critical | `docs/SPEC.md` | Update to clarify hard limit vs config default |
| **C2** | Hard limits consistency check | P2 Cosmetic | `docs/RUNBOOK.md` | Verify match with `hard_limits.py` |
| **C3** | Python version inconsistency | P1 Confusing | Multiple files | Standardize to 3.10+ |
| **E1** | Garbled UTF-8 characters (`🔴` → `ðŸ”´`, `✓` → `âœ“`, `—` → `â€”`) | P0 Critical | `PHASE_E_PLAN.md`, `NEXT.md`, `AUDIT_REPORT.md`, `QA_VALIDATION_PLAN.md` | Re-encode as UTF-8 |
| **R1** | Reference to non-existent `docs/RELEASE_READINESS.md` | P1 Confusing | Audit reports | Remove or point to QA_VALIDATION_PLAN.md |
| **R2** | Stale reference to `scripts/replay.ps1` | P1 Confusing | `docs/ORCHESTRATION.md` | Remove or mark as Planned |
| **R3** | Reference to non-existent `docs/EVENTS.md` marked complete | P1 Confusing | `docs/PHASE_E_PLAN.md` | Uncheck or mark as Planned |
| **R4** | References to planned docs (CONFIG, STRATEGIES) | P2 Cosmetic | `docs/PHASE_E_PLAN.md` | Ensure marked as Planned |
| **D1** | `docs/AUDIT_REPORT.md` marked SUPERSEDED but lacks clear redir | P2 Cosmetic | `docs/AUDIT_REPORT.md` | Add clear deprecation notice pointing to SPEC.md |
| **D2** | Duplication: `AGENTS.md` vs `DEV_AGENTS.md` naming confusion | P2 Cosmetic | Both files | Clarify: AGENTS=Runtime Logic, DEV_AGENTS=Developer Rules |
| **F1** | Inconsistent Status labels (case and presence) | P2 Cosmetic | Multiple files | Standardize to `> **Status**: ACTIVE` |
| **F2** | Inconsistent table alignment | P2 Cosmetic | Multiple | Standardize to left-align `:---` |
| **F3** | Missing language tags on code blocks | P2 Cosmetic | Multiple | Add specific tags (`powershell`, `python`, `json`) |

---

## 5. Canonical Source & Conflict Resolution Rules

### Source of Truth Hierarchy

```
1. Source Code (hard_limits.py, pyproject.toml) — ABSOLUTE
2. docs/SPEC.md — Authoritative documentation
3. config/default.json — Runtime defaults (can differ from hard limits)
4. docs/RUNBOOK.md — Operational procedures
5. README.md — User-facing quickstart
6. Other docs — Supporting context
```

### Specific Resolution Decisions

| Conflict | Decision | Justification |
|----------|----------|---------------|
| `MIN_RR_RATIO`: SPEC.md vs code | SPEC.md updated to: "Hard limit 1.0R (code); Config default 1.5R" | SPEC.md line 78 already correct per task.md |
| Python version: 3.10+ vs 3.11+ | Keep 3.10+ | `pyproject.toml` is authoritative; 3.10 supports match statements |
| Max Leverage: 20x | Verified consistent | `hard_limits.py` and `docs/RUNBOOK.md` both say 20x |
| Max Position Size: $200,000 | Verified consistent | `hard_limits.py` and `docs/RUNBOOK.md` both say $200,000 |
| Max Daily Loss: $50 | Verified consistent | `hard_limits.py` says $50, `docs/RUNBOOK.md` says $50 |

---

## 6. Markdown Style Guide

### Header Rules

| Rule | Example | Applies To |
|------|---------|------------|
| Use Sentence case for headers | `## System Requirements` not `## SYSTEM REQUIREMENTS` | All H2+ headers |
| H1 is file title only | One `#` per file | All files |
| Status block after H1 | `> **Status**: ACTIVE` | All docs/ files |

### Status Values

| Value | Meaning |
|-------|---------|
| `ACTIVE` | Current, maintained, authoritative |
| `IN PROGRESS` | Actively being developed |
| `DRAFT` | Incomplete, subject to change |
| `SUPERSEDED` | Replaced by another document |
| `DEPRECATED` | Scheduled for removal |

### Code Block Rules

| Rule | Correct | Incorrect |
|------|---------|-----------|
| Always specify language | ` ```powershell ` | ` ``` ` |
| Use `powershell` for PS | ` ```powershell ` | ` ```ps1 ` or ` ```shell ` |
| Use `python` for Python | ` ```python ` | ` ```py ` |
| Use `json` for JSON | ` ```json ` | ` ```javascript ` |

---

## 7. Step-by-Step Execution Plan

### Phase 0: Pre-Flight Verification

**Duration**: 2 minutes

```powershell
# Step 0.1: Verify clean working directory
git status --porcelain

# Step 0.2: Create safety checkpoint
git stash push -m "pre-docs-cleanup-checkpoint" --include-untracked

# Step 0.3: Verify compilation
python -m compileall src -q

# Step 0.4: Verify quick tests pass
.\scripts\verify.ps1 -Mode quick
```

---

### Phase 1: Encoding Standardization

**Duration**: 5 minutes  
**Goal**: Resolve garbled UTF-8 characters in priority files.

#### Step 1.1: Fix Garbled Characters
Search and replace garbled patterns in the following files:
- `docs/PHASE_E_PLAN.md` (ðŸ”´ → 🔴, ðŸŸ¡ → 🟡, ðŸŸ¢ → 🟢)
- `docs/NEXT.md` (âœ“ → ✓, â€” → —)
- `docs/AUDIT_REPORT.md` (âœ“ → ✓, â€” → —)
- `docs/QA_VALIDATION_PLAN.md` (â˜  → ☐, â‰¤ → ≤, â‰¥ → ≥)

#### Step 1.2: Verification Command
```powershell
Select-String -Path "docs\*.md" -Pattern "ðŸ", "âœ", "â€”" -List
# Expected: No matches
```

---

### Phase 2: Conflict Resolution

**Duration**: 5 minutes

#### Step 2.1: Verify SPEC.md and RUNBOOK.md
Confirm hard limits align with `src/laptop_agents/core/hard_limits.py`.
- `MAX_POSITION_SIZE_USD`: 200,000
- `MAX_DAILY_LOSS_USD`: 50
- `MAX_LEVERAGE`: 20.0
- `MIN_RR_RATIO`: 1.0 (Hard limit)

---

### Phase 3: Reference & Naming Cleanup

**Duration**: 10 minutes

#### Step 3.1: Audit PHASE_E_PLAN.md Checkmarks
- Ensure `docs/EVENTS.md`, `docs/CONFIG.md`, `docs/STRATEGIES.md` are marked `[ ]` (unchecked) as they do not exist yet.

#### Step 3.2: Clarify Naming (Issue D2)
- Add a brief note in `docs/AGENTS.md` and `docs/DEV_AGENTS.md` to distinguish between the two.
  - `AGENTS.md`: Technical documentation of the runtime agent modules.
  - `DEV_AGENTS.md`: Behavioral rules and safety protocols for AI coding assistants.

---

### Phase 4: Status Header Synchronization

**Duration**: 5 minutes

#### Step 4.1: Standardize Headers
Ensure all files in `docs/` have standard Title Case status: `> **Status**: [ACTIVE|IN PROGRESS|SUPERSEDED]`.
- Specific check: `GATES.md`, `ORCHESTRATION.md`, `VERIFY.md`, `RUNBOOK.md` (Verify already correct).

---

### Phase 5: Code Block & Table Formatting

**Duration**: 10 minutes

#### Step 5.1: Missing Language Tags
Audit and fix missing language tags in:
- `docs/RUNBOOK.md`
- `docs/PHASE_E_PLAN.md`
- `docs/QA_VALIDATION_PLAN.md`

#### Step 5.2: Table Alignment
Ensure all tables in `docs/` use left-alignment syntax `:---`.

---

### Phase 6: Verification & Commit

**Duration**: 5 minutes

#### Step 6.1: Run Full Verification
```powershell
python -m compileall src -q
.\scripts\verify.ps1 -Mode quick
```

#### Step 6.2: Final Commit
```powershell
git add -A
git commit -m "docs: comprehensive encoding and alignment cleanup

- Fixed UTF-8 garbled characters in PHASE_E_PLAN, NEXT, AUDIT_REPORT, and QA_VALIDATION_PLAN
- Standardized status headers across all docs
- Clarified distinction between AGENTS.md and DEV_AGENTS.md
- Updated PHASE_E_PLAN checkmarks for non-existent files
- Ensured consistent code block tagging and table alignment"
```

---

## 8. Files & Artifacts to Be Created/Modified

### Files to UPDATE

| File | Changes |
|------|---------|
| `docs/PHASE_E_PLAN.md` | Encoding fixes (🔴, 🟡, 🟢), checkmarks cleanup, tags |
| `docs/NEXT.md` | Encoding fixes (✓, —) |
| `docs/AUDIT_REPORT.md` | Encoding fixes (✓, —), Deprecation notice |
| `docs/QA_VALIDATION_PLAN.md` | Encoding fixes (☐, ≤, ≥), tags |
| `docs/AGENTS.md` | Cross-reference to DEV_AGENTS.md |
| `docs/DEV_AGENTS.md` | Cross-reference to AGENTS.md |
| `docs/RUNBOOK.md` | Table alignment and language tags |

---

## 9. Acceptance Criteria

| # | Criterion | Verification Command | Expected Result |
|---|-----------|---------------------|-----------------|
| 1 | No compilation errors | `python -m compileall src -q` | Exit code 0 |
| 2 | No garbled UTF-8 | `Select-String -Path "docs\*.md" -Pattern "ðŸ", "âœ"` | No matches |
| 3 | Unified Status Headers | `Select-String -Path "docs\*.md" -Pattern "STATUS:"` | No matches (all Title Case) |
| 4 | Distinct agent docs | Manual check of AGENTS.md / DEV_AGENTS.md | Clear distinction found |
| 5 | Verify script passes | `.\scripts\verify.ps1 -Mode quick` | `VERIFY: PASS` |

---

## 10. Rollback & Safety Strategy

- **Safety Checkpoint**: Created in Step 0.2 (`git stash`).
- **Rollback**: `git reset --hard HEAD` and `git stash pop`.

*End of Implementation Plan*
