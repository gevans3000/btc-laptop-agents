from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone


class LocalMemoryStore:
    """
    Simple append-only JSONL store. Local-only. Never sync unless you commit files yourself.
    """

    def __init__(self, data_dir: str, namespace: str = "default"):
        self.base = Path(data_dir)
        self.base.mkdir(parents=True, exist_ok=True)
        self.path = self.base / f"memory_{namespace}.jsonl"

    def add(self, role: str, content: str, meta: dict | None = None) -> None:
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "role": role,
            "content": content,
            "meta": meta or {},
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def tail(self, n: int = 20) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        out = []
        for line in lines[-n:]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
