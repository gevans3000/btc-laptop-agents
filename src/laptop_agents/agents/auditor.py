from __future__ import annotations

import json
import time
import asyncio
from pathlib import Path
from typing import Dict, Any, List
from laptop_agents.core.logger import logger


class AuditorAgent:
    """
    Shadow Auditor that trails the primary agent by monitoring the event stream.
    It verifies invariants and safety constraints on the *verified facts* emitted by the primary agent.
    """

    def __init__(self, workspace_dir: Path, lag_events: int = 10):
        self.workspace_dir = workspace_dir
        self.events_path = workspace_dir / "paper" / "events.jsonl"
        self.processed_count = 0
        self.lag_events = lag_events
        self.running = False
        self.alerts: List[Dict[str, Any]] = []

    async def run(self):
        """Main audit loop."""
        self.running = True
        logger.info("Starting Auditor Agent (Shadow Mode)...")

        while self.running:
            if not self.events_path.exists():
                logger.warning(f"Waiting for event stream at {self.events_path}...")
                await asyncio.sleep(2)
                continue

            try:
                new_events = self._read_new_events()

                # Maintain 'lag' by buffering or just processing up to len - lag
                # For simplicity, we process everything but we emphasize we are observing past events.

                for event in new_events:
                    self._audit_event(event)
                    self.processed_count += 1

                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Auditor crash: {e}")
                await asyncio.sleep(5)

    def _read_new_events(self) -> List[Dict[str, Any]]:
        """Read only new lines from the JSONL file."""
        events = []
        try:
            with open(self.events_path, "r", encoding="utf-8") as f:
                # Seek to last known position?
                # Ideally we keep file handle open, but for robustness (log rotation), we might reopen.
                # Simplest approach for now: Read all, skip processed. IN EFFICIENT for long runs.
                # Optimization: Seek.

                # For now, let's just read from line `processed_count`
                for _ in range(self.processed_count):
                    f.readline()

                for line in f:
                    if line.strip():
                        try:
                            events.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except FileNotFoundError:
            pass
        return events

    def _audit_event(self, event: Dict[str, Any]):
        """Apply rules to a single event."""
        event_type = event.get("event")

        # Rule 1: Price Sanity
        if event_type == "AsyncHeartbeat":
            price = event.get("price", 0)
            if price <= 0:
                self._alert(f"Zero/Negative Price detected: {price}", event)

        # Rule 2: Drawdown Check
        if event_type == "AsyncHeartbeat":
            equity = event.get("equity", 0)
            # Hardcoded check for example, could be config driven
            if equity < 5000:
                self._alert(f"Critical Equity Level: {equity}", event)

        # Rule 3: Fat Finger Check (Fill)
        if event_type == "Fill":
            qty = event.get("qty", 0)
            if qty > 5.0:  # Arbitrary large BTC amount
                self._alert(f"Large Position Fill detected: {qty} BTC", event)

    def _alert(self, message: str, context: Dict[str, Any]):
        alert = {"ts": time.time(), "message": message, "context": context}
        self.alerts.append(alert)
        logger.error(f"[AUDITOR ALERT] {message} | Ctx: {context.get('event')}")


if __name__ == "__main__":
    # Assume running from repo root
    workspace = Path(".workspace")
    auditor = AuditorAgent(workspace)
    try:
        asyncio.run(auditor.run())
    except KeyboardInterrupt:
        pass
