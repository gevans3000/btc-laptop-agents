from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import json
import uuid
from typing import Any, Dict, Iterable, List, Union


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


PathLike = Union[str, Path]


class PaperJournal:
    """Append-only JSONL paper-trade journal.

    Events:
      - trade:  {"type":"trade", ...}
      - update: {"type":"update", ...}
    """

    def __init__(self, path: PathLike = "data/paper_journal.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def new_trade(
        self,
        *,
        instrument: str,
        timeframe: str,
        direction: str,
        plan: Dict[str, Any],
        trade_id: str | None = None,
    ) -> str:
        tid = trade_id or f"PT-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        event = {
            "type": "trade",
            "trade_id": tid,
            "created_at": _now_iso(),
            "instrument": instrument,
            "timeframe": timeframe,
            "direction": direction,
            "plan": plan,
        }
        self._append(event)
        return tid

    def add_update(self, trade_id: str, update: Dict[str, Any]) -> None:
        event = {"type": "update", "trade_id": trade_id, "at": _now_iso(), **update}
        self._append(event)

    def iter_events(self) -> Iterable[Dict[str, Any]]:
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def last(self, n: int = 5) -> List[Dict[str, Any]]:
        events = list(self.iter_events())
        return events[-n:]

    def _append(self, obj: Dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
