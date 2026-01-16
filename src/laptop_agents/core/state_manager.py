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
        backup_path = self.state_file.with_suffix(".bak")
        for try_path in [self.state_file, backup_path]:
            if not try_path.exists():
                continue
            try:
                with open(try_path) as f:
                    self._state = json.load(f)
                logger.info(f"Loaded state from {try_path}")
                return
            except Exception as e:
                logger.error(f"Failed to load state from {try_path}: {e}")
                if try_path == self.state_file:
                    # Move corrupt file
                    try:
                        self.state_file.rename(self.state_file.with_suffix(f".corrupt.{int(time.time())}"))
                    except Exception:
                        pass
        self._state = {}
    
    def save(self) -> None:
        """Atomic save via temp file + rename + backup."""
        self._state["last_saved"] = time.time()
        temp = self.state_file.with_suffix(".tmp")
        backup = self.state_file.with_suffix(".bak")
        
        try:
            with open(temp, "w") as f:
                json.dump(self._state, f, indent=2)
            
            # Step 2: Backup current (if exists and valid)
            if self.state_file.exists():
                try:
                    import shutil
                    shutil.copy2(self.state_file, backup)
                except Exception:
                    pass
            
            # Step 3: Atomic rename
            temp.replace(self.state_file)
        except Exception as e:
            logger.error(f"Failed to save unified state: {e}")
    
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
