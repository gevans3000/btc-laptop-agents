# Markdown Documentation Audit Report
> **Date**: 2026-01-12
> **Auditor**: Antigravity AI
> **Scope**: All 20 `.md` files in `btc-laptop-agents`

---

## Executive Summary

| Category | Count | Severity |
|----------|-------|----------|
| **Critical Conflicts** | 3 | 🔴 HIGH |
| **Duplicate/Redundant Files** | 2 | 🟡 MEDIUM |
| **Outdated References** | 6 | 🟡 MEDIUM |
| **Inconsistent Formatting** | 4 | 🟢 LOW |
| **Missing/Broken Links** | 3 | 🟡 MEDIUM |
| **Status Marker Issues** | 2 | 🟢 LOW |

---

## 1. Critical Conflicts 🔴

### 1.1 Hard Limits Contradiction: `MIN_RR_RATIO` vs `rr_min`

| Location | Value | Notes |
|----------|-------|-------|
| `hard_limits.py` (Code) | `MIN_RR_RATIO = 1.0` | Actual enforced value |
| `docs/SPEC.md` (Line 78) | `1.5R` | Claims "Risk/Reward: Minimum 1.5R" |
| `config/default.json` | `rr_min: 1.5` | Config says 1.5 |
| `docs/QA_VALIDATION_PLAN.md` | `rr_min ≥ 1.0` | Says 1.0 |

**Conflict**: The code enforces `MIN_RR_RATIO = 1.0` as the absolute floor, but `SPEC.md` claims the minimum is 1.5R. This is contradictory authoritative guidance.

**Recommendation**:
- Update `docs/SPEC.md` to clarify: "Hard limit: 1.0R minimum; Config default: 1.5R"
- OR change `hard_limits.py` to `MIN_RR_RATIO = 1.5` if 1.5R is truly required

---

### 1.2 Python Version Not Explicitly Documented

| Location | Value |
|----------|-------|
| `README.md` (Line 178) | `Python 3.10+` |
| `docs/RUNBOOK.md` | `Python: 3.10 or higher` |
| All other docs | No mention |

**Issue**: Python version is only mentioned in 2 files. Other docs that discuss environment setup don't reference it.

**Recommendation**: Add Python version requirement to `docs/SPEC.md` under Requirements section.

---

### 1.3 File Reference with Encoding Issues

Multiple files show **`â€"` instead of `—` (em-dash)** and **`→` garbled characters**:

| File | Issue |
|------|-------|
| `docs/DEV_AGENTS.md` | Line 1: `â€"` |
| `docs/AI_HANDOFF.md` | Line 1: `â€"` |
| `docs/MAP.md` | Line 1: `â€"` |
| Multiple files | Garbled Unicode throughout |

**Cause**: UTF-8 encoding with BOM or Windows-1252 encoding mismatch.

**Recommendation**: Re-save all affected files as UTF-8 without BOM.

---

## 2. Duplicate/Redundant Files 🟡

### 2.1 `ASSISTANT_CONTEXT.md` vs `AI_HANDOFF.md`

Both files serve the same purpose: providing context for AI agents.

| File | Lines | Content |
|------|-------|---------|
| `docs/ASSISTANT_CONTEXT.md` | ~50 | Legacy context file, mentions "sync packs" |
| `docs/AI_HANDOFF.md` | ~32 | Updated context file, no sync pack references |

**Conflict**: `ASSISTANT_CONTEXT.md` is outdated and redundant.

**Recommendation**:
- Delete `docs/ASSISTANT_CONTEXT.md`
- Update `docs/START_HERE.md` to only reference `AI_HANDOFF.md`

---

### 2.2 `AUDIT_REPORT.md` Contains Duplicate Content

`docs/AUDIT_REPORT.md` has TWO audit sections:
1. Lines 1-90: "Documentation & Operations Audit"
2. Lines 95-200: "Final Audit Checklist" (overlapping content)

**Issue**: Redundant information with slight variations.

**Recommendation**: Consolidate into a single authoritative audit structure.

---

## 3. Outdated References 🟡

### 3.1 Missing Referenced Files

| Reference In | Referenced File | Status |
|--------------|-----------------|--------|
| `docs/AUDIT_REPORT.md` (Line 176) | `docs/RELEASE_READINESS.md` | ❌ Does not exist |
| `docs/PHASE_E_PLAN.md` (Line 256) | `docs/EVENTS.md` | ❌ Does not exist (marked as done) |
| `docs/ORCHESTRATION.md` (Line 49) | `scripts/replay.ps1` | ❌ Does not exist |
| `docs/PHASE_E_PLAN.md` (Lines 260-262) | `docs/CONFIG.md`, `docs/STRATEGIES.md` | ❌ Do not exist |

**Recommendation**:
- Create the missing files OR
- Remove/update the references to indicate they are planned

---

### 3.2 Sync Pack References (Deleted Feature)

`docs/AUDIT_REPORT.md` still references deleted sync pack files with strikethrough:
- `scripts/make_~~sync_pack~~.ps1`
- `~~assistant_sync_pack~~.md`

**Issue**: Uses non-standard markdown strikethrough syntax and mentions deleted features.

**Recommendation**: Remove all sync pack references entirely since the feature is deleted.

---

### 3.3 `exec_engine.py` Line Number Reference

| File | Reference |
|------|-----------|
| `docs/AUDIT_REPORT.md` (Line 126) | "File ends cleanly after `run_live_paper_trading` return (line 481)" |

**Issue**: Line number references become outdated with any code changes.

**Recommendation**: Remove specific line number references or convert to function name references only.

---

## 4. Inconsistent Formatting 🟢

### 4.1 Status Labels Inconsistency

| File | Format Used |
|------|-------------|
| `docs/GATES.md` | `> **STATUS**: ACTIVE` |
| `docs/VERIFY.md` | `> **STATUS**: ACTIVE` |
| `docs/ORCHESTRATION.md` | `> **STATUS**: ACTIVE` |
| `docs/TESTING.md` | `> **Status**: DRAFT` (lowercase "status") |
| `docs/SPEC.md` | `> **Status**: ACTIVE & AUTHORITATIVE` (different format) |
| Other docs | No status label |

**Recommendation**: Standardize all docs to use `> **Status**: [ACTIVE|DRAFT|DEPRECATED]`

---

### 4.2 Table Alignment Inconsistency

Some files use `:---` (left align) while others use `:---:` (center) or no alignment:

| File | Issue |
|------|-------|
| `docs/MAP.md` | Uses `:---` consistently ✓ |
| `docs/AUDIT_REPORT.md` | Mixed alignment |
| `docs/QA_VALIDATION_PLAN.md` | Garbled table formatting (encoding issue) |

---

### 4.3 Default Mode Inconsistency

| Location | Default Mode |
|----------|--------------|
| `docs/AUDIT_REPORT.md` | "Default Mode: `single` (code default) / `live` (script default)" |
| `docs/SPEC.md` | Shows `single` as default |
| `README.md` | Shows 6 scripts, implies `live` for background |

**Issue**: Ambiguity about what "default" means.

**Recommendation**: Clarify in `SPEC.md` with explicit table showing code default vs script default.

---

## 5. Missing/Broken Internal Links 🟡

### 5.1 START_HERE.md Links

All links in `docs/START_HERE.md` are relative and work correctly ✓

### 5.2 Cross-References That May Break

| From | To | Status |
|------|----|--------|
| `AI_HANDOFF.md` → `START_HERE.md` | Context loading | ⚠️ Circular reference |
| `DEV_AGENTS.md` → `SPEC.md` | "Read SPEC.md" | ✓ Works |
| `DEV_AGENTS.md` → `MAP.md` | Line ranges | ⚠️ Stale if code changes |

---

## 6. Content Organization Issues

### 6.1 AGENTS.md vs DEV_AGENTS.md Overlap

| File | Purpose | Audience |
|------|---------|----------|
| `docs/AGENTS.md` | Architecture/Collaboration | Mixed (Humans + AI) |
| `docs/DEV_AGENTS.md` | Development Rules | AI Agents |

**Issue**: Both discuss "agents" but for different purposes. Names are confusing.

**Recommendation**: Rename `AGENTS.md` → `ARCHITECTURE.md` to clarify purpose.

---

### 6.2 PHASE_E_PLAN.md Contains Stale Checkmarks

`docs/PHASE_E_PLAN.md` has items marked `[x]` as complete, but:
- Some referenced files don't exist (`docs/EVENTS.md`)
- Some tasks marked complete may not be verified

**Recommendation**: Audit all `[x]` items for accuracy.

---

## 7. Recommendations Summary

### Priority 1 (Critical - Fix Immediately)

| # | Action | Files Affected |
|---|--------|----------------|
| 1 | Align `MIN_RR_RATIO` documentation with code | `SPEC.md`, `QA_VALIDATION_PLAN.md` |
| 2 | Fix UTF-8 encoding on all garbled files | `DEV_AGENTS.md`, `AI_HANDOFF.md`, `MAP.md`, etc. |
| 3 | Delete redundant `ASSISTANT_CONTEXT.md` | `ASSISTANT_CONTEXT.md`, `START_HERE.md` |

### Priority 2 (Medium - Fix Soon)

| # | Action | Files Affected |
|---|--------|----------------|
| 4 | Remove references to non-existent `RELEASE_READINESS.md` | `AUDIT_REPORT.md` |
| 5 | Remove references to non-existent `replay.ps1` | `ORCHESTRATION.md` |
| 6 | Clean up sync pack references | `AUDIT_REPORT.md` |
| 7 | Update `PHASE_E_PLAN.md` checkmarks | `PHASE_E_PLAN.md` |

### Priority 3 (Low - Quality Improvement)

| # | Action | Files Affected |
|---|--------|----------------|
| 8 | Standardize Status labels across all docs | All docs |
| 9 | Remove line number references | `AUDIT_REPORT.md` |
| 10 | Rename `AGENTS.md` → `ARCHITECTURE.md` | `AGENTS.md`, `START_HERE.md` |

---

## Appendix: File Inventory

| File | Status | Notes |
|------|--------|-------|
| `README.md` | ✓ Active | Primary entry point |
| `docs/AGENTS.md` | ⚠️ Review | Consider rename |
| `docs/AI_HANDOFF.md` | ⚠️ Encoding | Fix character encoding |
| `docs/API_REFERENCE.md` | ✓ Active | Current API docs |
| `docs/ASSISTANT_CONTEXT.md` | ❌ Delete | Redundant with AI_HANDOFF |
| `docs/AUDIT_REPORT.md` | ⚠️ Review | Has duplicate sections + stale refs |
| `docs/DEV_AGENTS.md` | ⚠️ Encoding | Fix character encoding |
| `docs/GATES.md` | ✓ Active | Safety gates documentation |
| `docs/GIT_WORKFLOW.md` | ✓ Active | Git commit policy |
| `docs/KNOWN_ISSUES.md` | ✓ Active | Issue tracking |
| `docs/MAP.md` | ⚠️ Encoding | Fix character encoding |
| `docs/NEXT.md` | ✓ Active | Roadmap |
| `docs/ORCHESTRATION.md` | ⚠️ Review | Refs non-existent replay.ps1 |
| `docs/PHASE_E_PLAN.md` | ⚠️ Review | Stale checkmarks |
| `docs/QA_VALIDATION_PLAN.md` | ⚠️ Encoding | Garbled table content |
| `docs/RUNBOOK.md` | ✓ Active | Operations manual |
| `docs/SPEC.md` | ⚠️ Review | MIN_RR conflict |
| `docs/START_HERE.md` | ⚠️ Review | Links to redundant file |
| `docs/TESTING.md` | ⚠️ Status DRAFT | May need promotion to ACTIVE |
| `docs/VERIFY.md` | ✓ Active | Verification protocol |

---

*End of Audit Report*
