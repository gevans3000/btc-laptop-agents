# ADR 001: SQLite WAL for Broker State Persistence

## Status
Accepted

## Context
The "Paper Broker" needs to persist trade state (positions, orders, history) across process restarts. Initially, simple JSON files were used, but they are prone to corruption during concurrent writes or sudden process kills.

## Decision
We use SQLite with **Write-Ahead Logging (WAL)** mode enabled.

## Consequences
- **Reliability**: Atomic commits prevent state corruption.
- **Concurrency**: WAL allows readers and writers to operate simultaneously without blocking.
- **Performance**: Faster writes than standard rollback journals.
- **Complexity**: Requires a thin ORM or raw SQL (we use light wrappers in `paper_broker.py`).
- **Auditability**: SQLite files are standard and can be inspected with external tools.
