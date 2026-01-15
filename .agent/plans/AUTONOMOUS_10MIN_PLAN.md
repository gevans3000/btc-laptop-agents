# Autonomous 10-Minute Paper Trading Completion Plan

**Objective**: Make the `btc-laptop-agents` paper-trading app run autonomously for 10 minutes on live/near-real-time market data with high reliability.

**Execution Mode**: `// turbo-all` — Auto-run ALL safe commands.

---

## Pre-Flight Verification

Before starting, verify the environment:

```powershell
# 1. Confirm virtual environment
.\.venv\Scripts\Activate.ps1

# 2. Confirm dependencies
pip install -e . --quiet

# 3. Run existing tests to establish baseline
python -m pytest tests/ -v --tb=short 2>&1 | Tee-Object -FilePath pytest_baseline.log
```

**Gate**: All existing tests must pass before proceeding.

---

## Phase 1: Secret Scrubbing (CRITICAL SECURITY)

**Why**: Prevents API keys from leaking into logs during autonomous runs or crash dumps.

### Task 1.1: Implement Log Scrubber

**File**: `src/laptop_agents/core/logger.py`

**Changes**:
1. Add a `SENSITIVE_PATTERNS` list containing regex patterns for API keys, secrets, and passwords.
2. Modify `JsonFormatter.format()` to scrub sensitive values before emitting.

```python
# Add after imports
import re
import os

SENSITIVE_PATTERNS = [
    r'(?i)(api[_-]?key|secret|password|token|auth)["\']?\s*[:=]\s*["\']?([A-Za-z0-9+/=_-]{16,})',
    r'(?i)Bearer\s+[A-Za-z0-9+/=_-]{20,}',
]

def scrub_secrets(text: str) -> str:
    """Replace sensitive values with ***."""
    # Also scrub any values from .env
    env_secrets = [v for k, v in os.environ.items() 
                   if any(x in k.upper() for x in ['KEY', 'SECRET', 'TOKEN', 'PASSWORD'])
                   and v and len(v) > 8]
    for secret in env_secrets:
        text = text.replace(secret, '***')
    for pattern in SENSITIVE_PATTERNS:
        text = re.sub(pattern, r'\1=***', text)
    return text
```

3. In `JsonFormatter.format()`, wrap the final JSON string:
```python
return scrub_secrets(json.dumps(log_entry, separators=(",", ":")))
```

### Task 1.2: Add Unit Test

**File**: `tests/test_secret_scrubbing.py` (CREATE)

```python
import os
import logging
from laptop_agents.core.logger import scrub_secrets, setup_logger

def test_scrub_env_secrets():
    os.environ["TEST_API_KEY"] = "supersecretkey12345678"
    result = scrub_secrets("My key is supersecretkey12345678")
    assert "supersecretkey12345678" not in result
    assert "***" in result
    del os.environ["TEST_API_KEY"]

def test_scrub_patterns():
    text = 'api_key="abc123456789012345"'
    result = scrub_secrets(text)
    assert "abc123456789012345" not in result
```

**Verify**:
```powershell
python -m pytest tests/test_secret_scrubbing.py -v
```

---

## Phase 2: Unified State Persistence

**Why**: Prevent loss of CircuitBreaker and Supervisor state on restart, which could violate risk limits.

### Task 2.1: Create State Manager

**File**: `src/laptop_agents/core/state_manager.py` (CREATE)

```python
"""
Unified state manager for crash recovery.
Persists broker, circuit breaker, and supervisor state atomically.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional
from laptop_agents.core.logger import logger

class StateManager:
    """Atomic state persistence for crash recovery."""
    
    def __init__(self, state_dir: Path):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / "unified_state.json"
        self._state: Dict[str, Any] = {}
        self._load()
    
    def _load(self) -> None:
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    self._state = json.load(f)
                logger.info(f"Loaded state from {self.state_file}")
            except Exception as e:
                logger.error(f"Failed to load state: {e}")
                self._state = {}
    
    def save(self) -> None:
        """Atomic save via temp file + rename."""
        self._state["last_saved"] = time.time()
        temp = self.state_file.with_suffix(".tmp")
        with open(temp, "w") as f:
            json.dump(self._state, f, indent=2)
        temp.replace(self.state_file)
    
    def get(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        self._state[key] = value
    
    def get_circuit_breaker_state(self) -> Dict[str, Any]:
        return self.get("circuit_breaker", {})
    
    def set_circuit_breaker_state(self, state: Dict[str, Any]) -> None:
        self.set("circuit_breaker", state)
    
    def get_supervisor_state(self) -> Dict[str, Any]:
        return self.get("supervisor", {})
    
    def set_supervisor_state(self, state: Dict[str, Any]) -> None:
        self.set("supervisor", state)
    
    def clear(self) -> None:
        self._state = {}
        if self.state_file.exists():
            self.state_file.unlink()
```

### Task 2.2: Integrate into AsyncSession

**File**: `src/laptop_agents/session/async_session.py`

**Changes**:
1. Import `StateManager` at the top.
2. In `AsyncRunner.__init__()`, add:
   ```python
   from laptop_agents.core.state_manager import StateManager
   self.state_manager = StateManager(PAPER_DIR)
   ```
3. In `on_candle_closed()`, after updating circuit breaker, add:
   ```python
   self.state_manager.set_circuit_breaker_state(self.circuit_breaker.get_status())
   self.state_manager.save()
   ```
4. At the start of `run()`, restore circuit breaker state if it exists.

### Task 2.3: Add Unit Test

**File**: `tests/test_state_manager.py` (CREATE)

```python
import tempfile
from pathlib import Path
from laptop_agents.core.state_manager import StateManager

def test_state_persistence():
    with tempfile.TemporaryDirectory() as td:
        sm = StateManager(Path(td))
        sm.set("test_key", {"value": 123})
        sm.save()
        
        # Simulate restart
        sm2 = StateManager(Path(td))
        assert sm2.get("test_key") == {"value": 123}

def test_circuit_breaker_state():
    with tempfile.TemporaryDirectory() as td:
        sm = StateManager(Path(td))
        sm.set_circuit_breaker_state({"tripped": False, "consecutive_losses": 2})
        sm.save()
        
        sm2 = StateManager(Path(td))
        state = sm2.get_circuit_breaker_state()
        assert state["consecutive_losses"] == 2
```

**Verify**:
```powershell
python -m pytest tests/test_state_manager.py -v
```

---

## Phase 3: WebSocket Connection Hardening

**Why**: Detect stale/half-open connections faster than the 30s watchdog.

### Task 3.1: Add Application-Level Heartbeat

**File**: `src/laptop_agents/data/providers/bitunix_ws.py`

**Changes**:
1. Add `last_message_time` tracking in `__init__`:
   ```python
   self.last_message_time: float = 0.0
   self.heartbeat_timeout_sec: float = 10.0
   ```

2. Update `_handle_messages()` to track message times:
   ```python
   # At the start of the for loop
   self.last_message_time = time.time()
   ```

3. Add a heartbeat check task in `listen()`:
   ```python
   async def _heartbeat_check(self):
       while self._running:
           await asyncio.sleep(2.0)
           if time.time() - self.last_message_time > self.heartbeat_timeout_sec:
               logger.warning(f"No WS message for {self.heartbeat_timeout_sec}s, forcing reconnect")
               self._running = False
               if self.ws:
                   await self.ws.close()
   ```

4. Start the heartbeat check as a task in `listen()`.

### Task 3.2: Add Pydantic Schema Validation

**File**: `src/laptop_agents/data/providers/bitunix_ws.py`

**Changes**:
1. Add at top of file:
   ```python
   from pydantic import BaseModel, ValidationError
   from typing import Optional
   
   class KlineMessage(BaseModel):
       time: str
       open: float
       high: float
       low: float
       close: float
       baseVol: Optional[float] = 0.0
   
   class TickerMessage(BaseModel):
       bidOnePrice: Optional[float] = 0.0
       askOnePrice: Optional[float] = 0.0
       lastPrice: float
       time: str
   ```

2. In `_handle_messages()`, wrap candle/ticker parsing with Pydantic:
   ```python
   try:
       validated = KlineMessage(**item)
       candle = Candle(
           ts=validated.time,
           open=validated.open,
           ...
       )
   except ValidationError as e:
       logger.error(f"Schema validation failed: {e}")
       continue
   ```

**Verify**:
```powershell
# Run a quick 1-minute async session to test WS
python -m src.laptop_agents.run --mode live-session --async --duration 1 --symbol BTCUSDT
```

---

## Phase 4: Working Order Management (Execution Realism)

**Why**: Real markets allow partial fills to remain on the book.

### Task 4.1: Add Working Order Tracking

**File**: `src/laptop_agents/paper/broker.py`

**Changes**:
1. Add to `__init__`:
   ```python
   self.working_orders: List[Dict[str, Any]] = []
   ```

2. Modify `_try_fill()` to handle partial fills:
   ```python
   if actual_qty < qty:
       # Create a working order for the remainder
       remainder = {
           "client_order_id": f"{client_order_id}_remainder",
           "side": side,
           "entry_type": "limit",
           "entry": fill_px,
           "qty": qty - actual_qty,
           "sl": sl,
           "tp": tp,
           "equity": equity,
           "created_at": time.time()
       }
       self.working_orders.append(remainder)
       logger.info(f"WORKING ORDER CREATED: {qty - actual_qty:.4f} remaining")
   ```

3. Add method to process working orders:
   ```python
   def _process_working_orders(self, candle: Any) -> List[Dict[str, Any]]:
       """Check if any working orders can be filled."""
       fills = []
       remaining = []
       for order in self.working_orders:
           if self.pos is None:  # Only fill if no position
               fill = self._try_fill(candle, order)
               if fill:
                   fills.append(fill)
               else:
                   remaining.append(order)
           else:
               remaining.append(order)
       self.working_orders = remaining
       return fills
   ```

4. Call `_process_working_orders()` at the start of `on_candle()`.

### Task 4.2: Add Unit Test

**File**: `tests/test_working_orders.py` (CREATE)

```python
from laptop_agents.paper.broker import PaperBroker
from laptop_agents.trading.helpers import Candle

def test_partial_fill_creates_working_order():
    broker = PaperBroker(symbol="BTCUSDT", fees_bps=0, slip_bps=0)
    
    # Create a candle with low volume to force partial fill
    candle = Candle(ts="2024-01-01T00:00:00", open=100.0, high=101.0, low=99.0, close=100.0, volume=0.1)
    
    order = {
        "go": True,
        "side": "LONG",
        "entry_type": "market",
        "entry": 100.0,
        "qty": 1.0,  # Request 1, but volume only allows 0.01 (10% of 0.1)
        "sl": 99.0,
        "tp": 102.0,
        "equity": 10000.0,
        "client_order_id": "test_001"
    }
    
    events = broker.on_candle(candle, order)
    
    # Should have partial fill and working order
    assert len(events["fills"]) == 1
    assert events["fills"][0].get("partial") == True
    assert len(broker.working_orders) == 1
```

**Verify**:
```powershell
python -m pytest tests/test_working_orders.py -v
```

---

## Phase 5: Deterministic Replay Harness

**Why**: Debug failures without waiting for live markets.

### Task 5.1: Create Replay Runner

**File**: `src/laptop_agents/backtest/replay_runner.py` (CREATE)

```python
"""
Deterministic replay runner for debugging and testing.
Replays recorded ticks/candles through the trading engine.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import AsyncGenerator, List, Union
from laptop_agents.trading.helpers import Candle, Tick
from laptop_agents.core.logger import logger

class ReplayProvider:
    """Replays recorded market data at realistic timestamps."""
    
    def __init__(self, events_file: Path, speed_multiplier: float = 1.0):
        self.events_file = Path(events_file)
        self.speed_multiplier = speed_multiplier
        self._events: List[dict] = []
        self._load()
    
    def _load(self) -> None:
        with open(self.events_file) as f:
            for line in f:
                if line.strip():
                    self._events.append(json.loads(line))
        logger.info(f"Loaded {len(self._events)} events for replay")
    
    async def listen(self) -> AsyncGenerator[Union[Candle, Tick], None]:
        """Yield events at recorded timestamps."""
        import asyncio
        
        last_ts = None
        for event in self._events:
            event_type = event.get("event", "")
            
            # Parse timestamp and sleep to maintain timing
            ts = event.get("ts") or event.get("timestamp")
            if ts and last_ts:
                # Simple delay based on ordering
                await asyncio.sleep(0.1 / self.speed_multiplier)
            last_ts = ts
            
            # Convert to Candle or Tick
            if "candle" in event_type.lower() or "kline" in event_type.lower():
                yield Candle(
                    ts=event.get("ts", ""),
                    open=float(event.get("open", 0)),
                    high=float(event.get("high", 0)),
                    low=float(event.get("low", 0)),
                    close=float(event.get("close", 0)),
                    volume=float(event.get("volume", 0))
                )
            elif "tick" in event_type.lower() or "heartbeat" in event_type.lower():
                if "candle_close" in event:
                    yield Tick(
                        symbol=event.get("symbol", "BTCUSDT"),
                        bid=float(event.get("candle_close", 0)),
                        ask=float(event.get("candle_close", 0)),
                        last=float(event.get("candle_close", 0)),
                        ts=event.get("ts", "")
                    )
```

### Task 5.2: Add CLI Flag for Replay Mode

**File**: `src/laptop_agents/run.py`

**Changes**:
Add argument:
```python
ap.add_argument("--replay", type=str, default=None, help="Path to events.jsonl for deterministic replay")
```

In the `live-session` block, check for replay mode:
```python
if args.replay:
    from laptop_agents.backtest.replay_runner import ReplayProvider
    # Use ReplayProvider instead of live WS
    logger.info(f"REPLAY MODE: Using {args.replay}")
```

---

## Phase 6: Docker & Makefile (DevEx)

**Why**: Reproducible runs on any machine.

### Task 6.1: Create Dockerfile

**File**: `Dockerfile` (CREATE at repo root)

```dockerfile
# Multi-stage build for lightweight runner
FROM python:3.11-slim AS base

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY src/ src/
COPY config/ config/
COPY pyproject.toml .

# Install package
RUN pip install -e .

# Create non-root user
RUN useradd -m trader
USER trader

# Default command
CMD ["python", "-m", "src.laptop_agents.run", "--mode", "live-session", "--async", "--duration", "10"]
```

### Task 6.2: Create Makefile

**File**: `Makefile` (CREATE at repo root)

```makefile
.PHONY: build test run-paper clean

build:
	docker build -t btc-laptop-agents:latest .

test:
	python -m pytest tests/ -v --tb=short

run-paper:
	python -m src.laptop_agents.run --mode live-session --async --duration 10 --symbol BTCUSDT

run-docker:
	docker run --rm -it --env-file .env btc-laptop-agents:latest

clean:
	rm -rf __pycache__ .pytest_cache runs/latest/*.jsonl logs/*.log
```

---

## Phase 7: Final Verification

### Task 7.1: Run Full Test Suite

```powershell
python -m pytest tests/ -v --tb=short 2>&1 | Tee-Object -FilePath pytest_final.log
```

**Gate**: All tests must pass.

### Task 7.2: Run 10-Minute Autonomous Session

```powershell
python -m src.laptop_agents.run --mode live-session --async --duration 10 --symbol BTCUSDT 2>&1 | Tee-Object -FilePath session_10min.log
```

**Success Criteria**:
1. Session runs for full 10 minutes without crash
2. `runs/latest/summary.html` is generated
3. `logs/system.jsonl` contains no unhandled exceptions
4. No secrets appear in any log file

### Task 7.3: Verify Artifacts

```powershell
# Check required files exist
Test-Path runs/latest/summary.html
Test-Path runs/latest/events.jsonl
Test-Path logs/system.jsonl

# Check no secrets in logs
Select-String -Path logs/*.log, logs/*.jsonl -Pattern "BITUNIX" -SimpleMatch
# Should return nothing or only "***"
```

---

## Commit Sequence

After each phase passes verification:

```powershell
git add -A
git commit -m "feat(reliability): <phase description>"
```

Final commit:
```powershell
git push origin main
```

---

## Troubleshooting

### WebSocket Connection Fails
- Check `BITUNIX_API_KEY` and `BITUNIX_API_SECRET` in `.env`
- Verify network connectivity
- Check Bitunix API status

### Tests Fail After Changes
- Run `python -m pytest tests/<failing_test>.py -v --tb=long`
- Check for import errors first
- Verify PYTHONPATH includes `src/`

### Session Stops Early
- Check `logs/alert.txt` for critical errors
- Review `runs/latest/events.jsonl` for the last event
- Look for `circuit_breaker_tripped` or `kill_switch` events
