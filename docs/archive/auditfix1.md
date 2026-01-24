# Audit Fix Prompt - BTC Laptop Agents

You are a senior Python engineer. Your task is to fix ALL issues in the btc-laptop-agents repository to bring it to production quality. Work autonomously without asking questions. Execute all changes, then verify with tests/lint/mypy.

## CONTEXT

This is a Python trading system at `c:/Users/lovel/trading/btc-laptop-agents`. Package is in `src/laptop_agents/`, tests in `tests/`.

## MANDATORY CHANGES - Execute ALL of these in order:

### 1. FIX FAILING TESTS (PermissionError in test_refactored_logic.py)

Edit `tests/conftest.py`:
- Replace the `local_tmp_path` fixture to use `tempfile.TemporaryDirectory()` context manager instead of manual `shutil.rmtree()`
- Ensure file handles are closed before cleanup
- Use `atexit` or proper context management

### 2. ADD COVERAGE TO CI

Edit `.github/workflows/ci.yml`:
- Add `pytest-cov` to the pip install step
- Change pytest run to: `pytest -q --tb=short --cov=laptop_agents --cov-report=xml --cov-fail-under=50`

Edit `pyproject.toml`:
- Add `"pytest-cov>=4.0.0"` to the `[project.optional-dependencies] test` list

### 3. ADD WINDOWS CI MATRIX

Edit `.github/workflows/ci.yml`:
- Add strategy matrix for `os: [ubuntu-latest, windows-latest]`
- Change `runs-on: ubuntu-latest` to `runs-on: ${{ matrix.os }}`

### 4. FIX EXCEPTION HANDLING - Create proper exception hierarchy

Create new file `src/laptop_agents/resilience/exceptions.py`:

```python
"""Typed exception hierarchy for trading operations."""

class TradingException(Exception):
    """Base for all trading-related errors."""
    pass

class PositionError(TradingException):
    """Errors related to position management."""
    pass

class PersistenceError(TradingException):
    """Errors saving/loading state."""
    pass

class OrderRejectedError(TradingException):
    """Order rejected by risk checks."""
    pass

class BrokerConnectionError(TradingException):
    """Connection to broker failed."""
    pass
```

Edit `src/laptop_agents/paper/broker.py`:
- Import the new exceptions at top
- In `_save_state()` method around lines 855-869: REMOVE the entire try/except block that writes `broker_state.json` (the JSON snapshot). Keep ONLY the SQLite `self.store.save_state()` call. This eliminates dual-write.
- Replace bare `except Exception as e: logger.warning(...)` patterns with specific exception types that either re-raise or trigger circuit breaker

### 5. DECOUPLE ORCHESTRATOR - Add Protocol interfaces

Create new file `src/laptop_agents/core/protocols.py`:

```python
"""Protocol interfaces for dependency injection."""
from __future__ import annotations
from typing import Protocol, Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from laptop_agents.trading.helpers import Candle

class BrokerProtocol(Protocol):
    def on_candle(self, candle: Any, order: Optional[Dict[str, Any]], tick: Optional[Any] = None) -> Dict[str, Any]: ...
    def save_state(self) -> None: ...
    def shutdown(self) -> None: ...
    def close_all(self, current_price: float) -> List[Dict[str, Any]]: ...
    @property
    def pos(self) -> Optional[Any]: ...
    @property
    def current_equity(self) -> float: ...

class ProviderProtocol(Protocol):
    def load_rest_candles(self, symbol: str, interval: str, limit: int) -> List[Any]: ...
    def get_instrument_info(self, symbol: str) -> Dict[str, Any]: ...

class StateManagerProtocol(Protocol):
    def save(self) -> None: ...
    def get(self, key: str, default: Any = None) -> Any: ...
    def set(self, key: str, value: Any) -> None: ...
```

Edit `src/laptop_agents/core/orchestrator.py`:
- Add import: `from laptop_agents.core.protocols import BrokerProtocol, ProviderProtocol`
- Keep existing imports but document they are concrete implementations
- Add type hints using Protocol types where appropriate

### 6. SPLIT LARGE FILES

#### 6a. Split broker.py

Create `src/laptop_agents/paper/broker_risk.py`:
- Move `_validate_risk_limits()` method and related risk validation logic
- Export as function that takes broker instance

Create `src/laptop_agents/paper/broker_state.py`:
- Move `_save_state()`, `_load_state()`, `_load_risk_config()`, `_load_exchange_config()` methods
- Export as mixin class `BrokerStateMixin`

Edit `src/laptop_agents/paper/broker.py`:
- Import from the new modules
- Use composition or mixin inheritance to integrate

#### 6b. Split bitunix_futures.py

Create `src/laptop_agents/data/providers/bitunix_signing.py`:
- Move `_sha256_hex()`, `build_query_string()`, `sign_rest()`, `sign_ws()` functions
- Move `_now_ms()` helper

Create `src/laptop_agents/data/providers/bitunix_websocket.py`:
- Move entire `BitunixWebsocketClient` class

Edit `src/laptop_agents/data/providers/bitunix_futures.py`:
- Import from the new modules
- Keep `BitunixFuturesProvider` class

### 7. ADD BITUNIX BROKER TESTS

Create `tests/test_bitunix_broker.py`:

```python
"""Unit tests for BitunixBroker with mocked provider."""
import pytest
from unittest.mock import MagicMock, patch
from laptop_agents.execution.bitunix_broker import BitunixBroker
from laptop_agents.trading.helpers import Candle
from datetime import datetime

@pytest.fixture
def mock_provider():
    provider = MagicMock()
    provider.symbol = "BTCUSDT"
    provider.fetch_instrument_info.return_value = {"tickSize": 0.01, "lotSize": 0.001, "minQty": 0.001}
    provider.get_pending_positions.return_value = []
    return provider

@pytest.fixture
def broker(mock_provider):
    return BitunixBroker(provider=mock_provider, starting_equity=10000.0)

def make_candle(close=50000.0):
    return Candle(ts=datetime.now().isoformat(), open=close, high=close+10, low=close-10, close=close, volume=100)

def test_broker_init(broker):
    assert broker.symbol == "BTCUSDT"
    assert broker.starting_equity == 10000.0

def test_no_order_no_action(broker):
    candle = make_candle()
    events = broker.on_candle(candle, None)
    assert events["fills"] == []
    assert events["exits"] == []

def test_rate_limit_enforcement(broker):
    from laptop_agents import constants
    candle = make_candle()
    order = {"go": True, "side": "LONG", "qty": 0.01, "entry": 50000, "sl": 49000, "tp": 52000, "equity": 10000}
    # Exhaust rate limit
    for _ in range(constants.MAX_ORDERS_PER_MINUTE + 1):
        broker.on_candle(candle, order)
    # Should have errors
    events = broker.on_candle(candle, order)
    assert len(broker.order_timestamps) <= constants.MAX_ORDERS_PER_MINUTE

def test_kill_switch_blocks_orders(broker, monkeypatch):
    monkeypatch.setenv("LA_KILL_SWITCH", "TRUE")
    candle = make_candle()
    order = {"go": True, "side": "LONG", "qty": 0.01}
    events = broker.on_candle(candle, order)
    assert "KILL_SWITCH_ACTIVE" in events.get("errors", [])
```

### 8. FIX PYDANTIC DEPRECATION

Edit `src/laptop_agents/core/config.py`:
- Replace `from pydantic import BaseModel, Field, validator` with `from pydantic import BaseModel, Field, field_validator`
- Change `@validator("symbol")` to `@field_validator("symbol", mode="before")`
- Update method signature from `def normalize_symbol(cls, v)` to `def normalize_symbol(cls, v: str) -> str`

### 9. CLEANUP DEAD FILES

Delete these files/add to .gitignore:
- Delete `src/laptop_agents/paper/broker_view.txt` if it exists
- Delete `test_state_broker.db` from repo root if it exists
- Add to `.gitignore`: `test_state_broker.db`, `local_pytest_temp/`, `pytest_temp/`

### 10. UPDATE EXPORTS

Edit `src/laptop_agents/resilience/__init__.py`:
- Add import for new exceptions: `from .exceptions import TradingException, PositionError, PersistenceError, OrderRejectedError, BrokerConnectionError`
- Add to `__all__`

## VERIFICATION - Run ALL of these after changes:

```powershell
cd c:\Users\lovel\trading\btc-laptop-agents
.venv\Scripts\python -m ruff check src tests
.venv\Scripts\python -m ruff format src tests
.venv\Scripts\python -m mypy src/laptop_agents --ignore-missing-imports --no-error-summary
.venv\Scripts\python -m pytest tests -q --tb=short
```

Fix any errors that arise from these commands before completing.

## RULES

- Do NOT ask questions - make reasonable decisions
- Do NOT skip any step
- Do NOT add unnecessary comments to code
- Maintain existing code style
- Run verification commands and fix any issues
- If a file split makes a file too small (<50 lines), merge related functionality
