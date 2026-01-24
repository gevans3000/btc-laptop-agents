# Task Spec: (Title of the Task)

## Role / Goal / Constraints
- **Role**: Senior Reliability Engineer.
- **Goal**: (Describe the specific objective here).
- **Constraints**:
  - Follow `docs/AI_ENGINEERING_PROTOCOL.md`.
  - Must not bypass hard ceilings in `src/laptop_agents/constants.py`.
  - (Add any task-specific constraints here).

## Failure Modes + Mitigations
1. **Failure**: (Describe failure 1)
   - **Mitigation**: (Describe mitigation 1)
2. **Failure**: (Describe failure 2)
   - **Mitigation**: (Describe mitigation 2)
3. **Failure**: (Describe failure 3)
   - **Mitigation**: (Describe mitigation 3)

## Acceptance Criteria
- [ ] (Criteria 1: e.g., Logic correctly handles X)
- [ ] (Criteria 2: e.g., No new dependencies added)
- [ ] (Criteria 3: e.g., State is persisted atomically)
- [ ] (Criteria 4: e.g., CLI command updated in Typer)

## Tests
- [ ] (Test 1: Describe unit test for happy path)
- [ ] (Test 2: Describe test for failure/edge case)
- [ ] **Command**: `pytest tests/test_filename.py`

## Rollback Plan
- **Detection**: (How to know this failed in production, e.g., check `events.jsonl` for errors)
- **Action**: (Step to revert, e.g., `git checkout HEAD~1` or specific manual cleanup)
