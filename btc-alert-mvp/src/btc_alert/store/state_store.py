import hashlib
import json
import time
from pathlib import Path


class AlertStateStore:
    def __init__(self, path: str = ".workspace/btc_alert_state.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def make_hash(message: str) -> str:
        return hashlib.sha256(message.encode("utf-8")).hexdigest()

    def should_send(self, message: str, cooldown_s: int) -> bool:
        data = self._read()
        now = int(time.time())
        msg_hash = self.make_hash(message)
        last_hash = data.get("last_hash")
        last_sent = int(data.get("last_sent_ts", 0))
        if msg_hash == last_hash and now - last_sent < cooldown_s:
            return False
        return True

    def mark_sent(self, message: str) -> None:
        self._write({"last_hash": self.make_hash(message), "last_sent_ts": int(time.time())})
