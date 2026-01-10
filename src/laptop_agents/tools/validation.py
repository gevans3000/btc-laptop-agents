"""
Validation tools for MVP artifacts.

These functions verify the integrity of events.jsonl, trades.csv, and summary.html.
Extracted from run.py during Phase 1 refactoring.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path


# Required keys for valid events.jsonl lines
REQUIRED_EVENT_KEYS = {"event", "timestamp"}

# Required columns for trades.csv
REQUIRED_TRADE_COLUMNS = {"trade_id", "side", "signal", "entry", "exit", "quantity", "pnl", "fees", "timestamp"}


def validate_events_jsonl(events_path: Path, append_event_fn=None) -> tuple[bool, str]:
    """Validate events.jsonl - each line must be valid JSON with required keys.
    
    Args:
        events_path: Path to events.jsonl file.
        append_event_fn: Optional callback to log validation errors.
    """
    if not events_path.exists():
        return False, f"events.jsonl does not exist at {events_path}"
    
    valid_lines = 0
    invalid_lines = 0
    with events_path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                # Check for required keys
                missing_keys = REQUIRED_EVENT_KEYS - set(obj.keys())
                if missing_keys:
                    invalid_lines += 1
                    if append_event_fn:
                        append_event_fn({"event": "EventsValidationError", "line": line_num, "missing_keys": list(missing_keys)})
                else:
                    valid_lines += 1
            except json.JSONDecodeError:
                invalid_lines += 1
                if append_event_fn:
                    append_event_fn({"event": "EventsValidationError", "line": line_num, "error": "invalid JSON"})
    
    if invalid_lines > 0:
        return False, f"events.jsonl: {valid_lines} valid, {invalid_lines} invalid lines"
    if valid_lines == 0:
        return False, "events.jsonl: no valid lines found"
    return True, f"events.jsonl: {valid_lines} valid lines"


def validate_trades_csv(trades_path: Path) -> tuple[bool, str]:
    """Validate trades.csv - must have required header columns and at least 1 data row."""
    if not trades_path.exists():
        return False, f"trades.csv does not exist at {trades_path}"
    
    try:
        with trades_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames or []
            
            # Check required columns
            missing_cols = REQUIRED_TRADE_COLUMNS - set(header)
            if missing_cols:
                return False, f"trades.csv: missing required columns: {sorted(missing_cols)}"
            
            # Count data rows
            rows = list(reader)
            if len(rows) == 0:
                return False, "trades.csv: no data rows (no trades executed)"
            
            return True, f"trades.csv: {len(rows)} trades, all required columns present"
    except Exception as e:
        return False, f"trades.csv: validation error - {e}"


def validate_summary_html(summary_path: Path) -> tuple[bool, str]:
    """Validate summary.html - must exist and have content."""
    if not summary_path.exists():
        return False, f"summary.html does not exist at {summary_path}"
    
    content = summary_path.read_text(encoding="utf-8")
    
    # Check for recognizable markers
    markers = ["<!doctype html>", "Run Summary", "run_id"]
    for marker in markers:
        if marker in content:
            return True, f"summary.html: contains marker '{marker}'"
    
    return False, "summary.html: no recognizable marker found"
