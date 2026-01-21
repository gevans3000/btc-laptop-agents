# AGENTS

## Review Rules
- Correctness: behavior matches intent and existing contracts.
- Security: protect secrets, validate inputs, and avoid unsafe side effects.
- Performance: avoid unnecessary IO/CPU; preserve async/scheduling assumptions.
- Edge cases: timeouts, retries, empty data, and network failures.
- Logging: keep logs actionable; avoid sensitive data.
- Error handling: fail fast on unsafe states; propagate critical errors.
- Style: match project conventions and typing expectations.

## How We Review (Checklist)
- Read the change and identify impacted modules and flows.
- Verify invariants and configuration precedence for session/runtime behavior.
- Run or review tests plus linters/type checks when relevant.
- Inspect error paths, retries, and circuit breakers for regressions.
- Check state persistence and artifact paths are unchanged or compatible.
- Note risks, missing tests, and next steps in the report.

## Repo Invariants
- Default trading symbol is normalized to uppercase without separators; default is BTCUSDT.
- Session artifacts live under repo root `.workspace` (see `SessionConfig.artifact_dir`).
- Strategy configs are loaded from `config/strategies/<name>.json` with precedence: overrides > config file > strategy defaults > built-in defaults.
- Environment variables with `LA_` prefix override session config; `LA_KILL_SWITCH=TRUE` forces `kill_switch`.
- Live execution requires `BITUNIX_API_KEY` and `BITUNIX_API_SECRET` to be set.
- Unified state is persisted atomically to `unified_state.json` with `.bak` backups in the chosen state directory.
- Position state is stored in SQLite WAL mode with a `state(symbol PRIMARY KEY)` table.
