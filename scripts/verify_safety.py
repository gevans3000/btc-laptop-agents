import sys
from pathlib import Path

# Add src to path
repo_root = Path(__file__).parent.parent
sys.path.append(str(repo_root / "src"))

from laptop_agents.agents.state import State
from laptop_agents.agents.risk_gate import RiskGateAgent
from laptop_agents.agents.supervisor import Supervisor
from laptop_agents.paper.broker import PaperBroker, Position
from laptop_agents.indicators import Candle


def test_risk_gate():
    print("Testing RiskGateAgent...")
    # 1. Test Funding Gate
    agent = RiskGateAgent({})
    state = State()
    state.order = {"go": True, "setup": {"name": "test"}}
    state.derivatives = {"flags": ["NO_TRADE_funding_hot"]}

    state = agent.run(state)
    assert state.order["go"] == False, "RiskGate failed to block NO_TRADE flag"
    assert "risk_gate_blocked" in state.order["reason"], "Incorrect block reason"
    print("  [PASS] Funding Gate blocked correctly")

    # 2. Test Max Risk Gate
    state = State()
    state.order = {"go": True, "risk_pct": 0.05}  # 5% risk > 2% limit
    state.derivatives = {"flags": []}

    state = agent.run(state)
    assert state.order["go"] == False, "RiskGate failed to block high risk"
    assert "exceeds hard limit" in state.order["reason"], "Incorrect block reason"
    print("  [PASS] Max Risk Gate blocked correctly")


def test_paper_broker_equity():
    print("\nTesting PaperBroker Equity...")
    broker = PaperBroker()

    # 1. No position
    assert broker.get_unrealized_pnl(100.0) == 0.0
    print("  [PASS] Empty position equity is 0")

    # 2. Long Position
    # Entry 50, Price 60, Qty 1 => +10
    broker.pos = Position(
        side="LONG", entry=50.0, qty=1.0, sl=40.0, tp=60.0, opened_at="t1"
    )
    pnl = broker.get_unrealized_pnl(60.0)
    assert abs(pnl - 10.0) < 1e-9, f"Long PnL incorrect: {pnl}"
    print("  [PASS] Long Position PnL correct")

    # 3. Short Position
    # Entry 50, Price 40, Qty 1 => +10
    broker.pos = Position(
        side="SHORT", entry=50.0, qty=1.0, sl=60.0, tp=40.0, opened_at="t1"
    )
    pnl = broker.get_unrealized_pnl(40.0)
    assert abs(pnl - 10.0) < 1e-9, f"Short PnL incorrect: {pnl}"
    print("  [PASS] Short Position PnL correct")


def test_supervisor_rounding():
    print("\nTesting Supervisor Rounding & Notional...")
    # Mocking Supervisor is hard due to deps, but we can verify logic by subclassing
    # or just trusting the code we wrote?
    # Let's try to instantiate with None providers, hope it works enough to call _resolve_order
    # _resolve_order needs state.order

    class MockCfg:
        def __getitem__(self, key):
            return {}

        def get(self, key, default=None):
            return {}

    # Minimal mock
    supervisor = Supervisor(
        provider=None,
        cfg={"derivatives_gates": {}, "setups": {}, "risk": {}},
        journal_path="temp_journal.jsonl",
    )

    state = State()
    # Setup conditions for a trade
    # Equity 10000, Risk 1% (100), SL dist 100 => Qty 1.0
    # Lot step 0.3 => Qty should be 0.9
    state.order = {
        "go": True,
        "entry": 50000.0,
        "sl": 49900.0,  # Dist 100
        "tp": 50200.0,
        "side": "LONG",
        "entry_type": "limit",
        "equity": 10000.0,
        "risk_pct": 0.01,
        "size_mult": 1.0,
        "rr_min": 1.0,
        "lot_step": 0.3,
        "min_notional": 5.0,
        "setup": {"name": "test"},
    }
    candle = Candle(ts="t1", open=50000, high=50000, low=50000, close=50000, volume=1)

    res = supervisor._resolve_order(state, candle)
    # Expected: Risk $100. Dist 100. Qty raw = 1.0.
    # Round to 0.3 => 0.9.
    qty = res["qty"]
    assert abs(qty - 0.9) < 1e-9, f"Rounding failed, got {qty}, expected 0.9"
    print("  [PASS] Lot Size Rounding correct")

    # Min Notional Fail
    state.order["entry"] = 10.0
    state.order["sl"] = 9.0  # Dist 1. Risk 100. Qty 100.
    state.order["min_notional"] = 2000.0  # 10 * 100 = 1000 < 2000

    res = supervisor._resolve_order(state, candle)
    assert res is None, "Min notional failed to block"
    print("  [PASS] Min Notional Block correct")


if __name__ == "__main__":
    try:
        test_risk_gate()
        test_paper_broker_equity()
        test_supervisor_rounding()
        print("\nALL SAFETY CHECKS PASSED ✅")
    except Exception as e:
        print(f"\nFAILED ❌: {e}")
        sys.exit(1)
