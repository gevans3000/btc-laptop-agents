"""Logging utilities for resilience patterns."""

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict
from laptop_agents.core.logger import logger


def log_event(
    event_type: str, data: Dict[str, Any], context: str = "exchange_call"
) -> None:
    """Log structured events."""
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": event_type,
        "context": context,
        **data,
    }

    # Log to logger
    logger.info(f"[RESILIENCE] {event_type}: {json.dumps(data, separators=(',', ':'))}")

    # Log to JSONL if enabled
    if os.environ.get("LAPTOP_AGENTS_LOG_JSONL"):
        log_path = os.environ.get("LAPTOP_AGENTS_LOG_JSONL", "resilience.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")


def log_provider_error(
    exchange_name: str, operation: str, error_type: str, details: str
) -> None:
    """Log provider-specific errors."""
    log_event(
        "provider_error",
        {
            "exchange": exchange_name,
            "operation": operation,
            "error_type": error_type,
            "details": details,
            "severity": "high",
        },
    )
