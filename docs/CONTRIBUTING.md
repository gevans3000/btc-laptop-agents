# Contributing to BTC Laptop Agents

## Philosophy
We treat this repository as a high-reliability financial system. Code is not just "merged"; it is verified, hardened, and proven safe.

## The AI Engineering Protocol
All changes must strictly adhere to the [AI Engineering Protocol](AI_ENGINEERING_PROTOCOL.md).
Key rules:
1. **Local-First**: No external dependencies for core logic.
2. **Deterministic**: Same input + Same seed = Same result.
3. **Artifact-Driven**: If it didn't log to `.workspace/`, it didn't happen.

## Development Workflow

### 1. Setup
```bash
# Install valid environment
pip install -e .[test]
# Verify
la doctor
```

### 2. Testing
We use `pytest` with a rigorous tiered approach:
```bash
# Fast tests (Unit)
pytest tests/unit

# Full suite (Integration + Regression)
pytest tests/
```

### 3. Safety Check
Before submitting PRs, verify you haven't altered `src/laptop_agents/constants.py` unless explicitly authorized. These are the safety rails.

## Documentation
- Update `ENGINEER.md` if changing CLI commands.
- Update `PROJECT_SCOPE.md` if changing architecture.
