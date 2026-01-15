from laptop_agents.trading.paper_journal import PaperJournal
import tempfile
import shutil
from pathlib import Path

def test_paper_journal_roundtrip():
    # Use explicit temp directory handling
    temp_dir = tempfile.mkdtemp()
    try:
        p = Path(temp_dir) / "paper_journal.jsonl"
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
    finally:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass
