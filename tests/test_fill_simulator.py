from laptop_agents.backtest.fill_simulator import FillSimulator
from dataclasses import dataclass


@dataclass
class MockCandle:
    low: float
    high: float


def test_fill_simulator_fixed_slippage():
    config = {"slippage_model": "fixed_bps", "slippage_bps": 10.0}
    sim = FillSimulator(config)

    # LONG Entry: price * (1 + 0.001)
    price = 100.0
    slipped = sim.apply_slippage(price, "LONG", is_entry=True)
    assert slipped == 100.1

    # LONG Exit: price * (1 - 0.001)
    slipped = sim.apply_slippage(price, "LONG", is_entry=False)
    assert slipped == 99.9


def test_fill_simulator_should_fill():
    sim = FillSimulator({})
    # Market always fills
    assert sim.should_fill({"entry_type": "market"}, None)

    # Limit fills if touched
    order = {"entry_type": "limit", "entry": 105}
    assert sim.should_fill(order, MockCandle(low=100, high=110))
    assert not sim.should_fill(order, MockCandle(low=100, high=104))
