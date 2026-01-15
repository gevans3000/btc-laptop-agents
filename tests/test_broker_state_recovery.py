import pytest
import json
import os
from pathlib import Path
from laptop_agents.paper.broker import PaperBroker, Position

def test_broker_state_recovery():
    state_file = Path("test_state_broker.json")
    if state_file.exists(): state_file.unlink()
    corrupt_suffix = ".corrupt"
    corrupt_file = Path(str(state_file) + corrupt_suffix)
    if corrupt_file.exists(): corrupt_file.unlink()
    
    try:
        # 1. Write a valid state file with open position
        initial_state = {
            "symbol": "BTCUSDT",
            "starting_equity": 10000.0,
            "current_equity": 9500.0,
            "processed_order_ids": ["order1"],
            "order_history": [{"type": "fill", "id": "order1"}],
            "working_orders": [],
            "pos": {
                "side": "LONG",
                "entry": 50000.0,
                "qty": 0.1,
                "sl": 49000.0,
                "tp": 52000.0,
                "opened_at": "2024-01-01T00:00:00Z",
                "entry_fees": 1.0,
                "bars_open": 5,
                "trail_active": False,
                "trail_stop": 0.0
            }
        }
        
        with open(state_file, "w") as f:
            json.dump(initial_state, f)
        
        # 2. Initialize PaperBroker
        broker = PaperBroker(symbol="BTCUSDT", state_path=str(state_file))
        
        # 3. Assert state is recovered
        assert broker.current_equity == 9500.0
        assert broker.pos is not None
        assert broker.pos.side == "LONG"
        assert broker.pos.entry == 50000.0
        assert "order1" in broker.processed_order_ids
        
        # 4. Write corrupt file
        with open(state_file, "w") as f:
            f.write("{ corrupt json ...")
        
        # 5. Assert broker initiates fresh
        broker2 = PaperBroker(symbol="BTCUSDT", state_path=str(state_file))
        assert broker2.current_equity == 10000.0
        assert broker2.pos is None
        assert corrupt_file.exists()
    finally:
        if state_file.exists(): state_file.unlink()
        if corrupt_file.exists(): corrupt_file.unlink()

if __name__ == "__main__":
    test_broker_state_recovery()
    print("test_broker_state_recovery PASSED")
