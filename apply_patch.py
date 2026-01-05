from __future__ import annotations

from pathlib import Path
import textwrap

FILES = {
    "src/laptop_agents/trading/paper_journal.py": r"""
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
    \"\"\"Lightweight JSONL (append-only) paper-trade journal.

    Format:
      - trade event: {"type":"trade", ...}
      - update event: {"type":"update", ...}
    \"\"\"

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
        event = {
            "type": "update",
            "trade_id": trade_id,
            "at": _now_iso(),
            **update,
        }
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
""",

    "src/laptop_agents/trading/__init__.py": r"""
from .paper_journal import PaperJournal

__all__ = ["PaperJournal"]
""",

    "tests/test_paper_journal.py": r"""
from laptop_agents.trading.paper_journal import PaperJournal


def test_paper_journal_roundtrip(tmp_path):
    p = tmp_path / "paper_journal.jsonl"
    j = PaperJournal(p)

    tid = j.new_trade(
        instrument="BTCUSDT",
        timeframe="5m",
        direction="LONG",
        plan={"entry": 112000, "sl": 111500, "tps": [112500, 113000]},
    )
    j.add_update(tid, {"note": "TP1 hit", "realized_r": 1.0})

    events = list(j.iter_events())
    assert events[0]["type"] == "trade"
    assert events[0]["trade_id"] == tid
    assert events[1]["type"] == "update"
    assert events[1]["trade_id"] == tid
""",
}


def _write(path: str, content: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    normalized = textwrap.dedent(content).lstrip("\n").rstrip() + "\n"
    p.write_text(normalized, encoding="utf-8")


def main() -> None:
    for path, content in FILES.items():
        _write(path, content)
    print("Patch applied: paper journal added.")


if __name__ == "__main__":
    main()
