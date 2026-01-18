from typing import Any, Dict
import json
import os
from datetime import datetime, timezone
import hashlib

from laptop_agents.core.logger import logger
from laptop_agents.constants import REPO_ROOT

# Directory constants
WORKSPACE_DIR = REPO_ROOT / ".workspace"
RUNS_DIR = WORKSPACE_DIR / "runs"
LATEST_DIR = RUNS_DIR / "latest"
PAPER_DIR = WORKSPACE_DIR / "paper"
LOGS_DIR = WORKSPACE_DIR / "logs"

# Global set to track event IDs for idempotency
EVENT_CACHE = set()


def utc_ts() -> str:
    """Get current UTC timestamp in ISO format with 'Z' suffix."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def append_event(obj: Dict[str, Any], paper: bool = False) -> None:
    # 5.3 Idempotent Event Logging
    event_id = obj.get("event_id")
    if not event_id:
        # Create stable ID from content (excluding timestamp/volatile fields if possible)
        # For simplicity, we use everything but the timestamp for the hash
        content = {k: v for k, v in obj.items() if k != "timestamp"}
        event_id = hashlib.md5(
            json.dumps(content, sort_keys=True).encode("utf-8")
        ).hexdigest()
        obj["event_id"] = event_id

    if event_id in EVENT_CACHE:
        return
    EVENT_CACHE.add(event_id)
    # Keep cache from growing too large
    if len(EVENT_CACHE) > 5000:
        # Remove oldest items (not strict LRU but works for basic deduplication)
        # Converting to list and slicing is inefficient but acceptable for this scale
        # Ideally we'd use a real LRU cache or deque
        list_cache = list(EVENT_CACHE)
        EVENT_CACHE.clear()
        EVENT_CACHE.update(list_cache[-2500:])

    obj.setdefault("timestamp", utc_ts())
    event_name = obj.get("event", "UnnamedEvent")
    logger.info(f"EVENT: {event_name}", obj)

    if paper:
        PAPER_DIR.mkdir(parents=True, exist_ok=True)  # Ensure parents exist
        with (PAPER_DIR / "events.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
    else:
        LATEST_DIR.mkdir(parents=True, exist_ok=True)
        with (LATEST_DIR / "events.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
