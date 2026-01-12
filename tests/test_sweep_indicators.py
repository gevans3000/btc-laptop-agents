import pytest
from src.laptop_agents.indicators import Candle, vwap, detect_sweep
from src.laptop_agents.agents.cvd_divergence import CvdDivergenceAgent
from src.laptop_agents.agents.state import State

def test_vwap_basic():
    candles = [
        Candle("2026-01-01T00:00:00Z", 100, 110, 90, 105, 10),
        Candle("2026-01-01T00:01:00Z", 105, 115, 100, 110, 20),
    ]
    v = vwap(candles)
    assert len(v) == 2
    # First candle typical price = (110+90+105)/3 = 101.66
    # Second candle typical price = (115+100+110)/3 = 108.33
    # Total CV = 101.66*10 + 108.33*20 = 1016.6 + 2166.6 = 3183.2
    # Total Vol = 30
    # VWAP = 3183.2 / 30 = 106.106...
    assert v[-1] > 106 and v[-1] < 107

def test_detect_sweep_long():
    level = 100.0
    candles = [
        Candle("1", 110, 115, 105, 108, 10),
        Candle("2", 108, 110, 98, 99, 10),  # Swept below 100
        Candle("3", 99, 105, 99, 102, 10), # Reclaimed above 100
    ]
    # side LONG means we swept below and reclaimed
    assert detect_sweep(candles, level, "LONG") == True

def test_cvd_divergence_agent():
    candles = [
        Candle("1", 100, 105, 95, 100, 100),
        Candle("2", 100, 105, 94, 99, 100),  # Price lower low
        Candle("3", 99, 104, 93, 101, 200),  # Price lower low, strong reclaim
    ]
    agent = CvdDivergenceAgent({"lookback": 2})
    state = State(candles=candles)
    state = agent.run(state)
    assert "cvd" in state.cvd_divergence
    assert len(state.cvd_divergence["cvd"]) == 3
