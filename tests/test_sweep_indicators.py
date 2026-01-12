import pytest
from src.laptop_agents.indicators import Candle, vwap, detect_sweep, cvd_indicator, ema
from src.laptop_agents.agents.cvd_divergence import CvdDivergenceAgent
from src.laptop_agents.agents.state import State
from src.laptop_agents.agents.setup_signal import SetupSignalAgent

def test_vwap_basic():
    candles = [
        Candle("2026-01-01T00:00:00Z", 100, 110, 90, 105, 10),
        Candle("2026-01-01T00:01:00Z", 105, 115, 100, 110, 20),
    ]
    v = vwap(candles)
    assert len(v) == 2
    # Typical prices: (110+90+105)/3 = 101.666, (115+100+110)/3 = 108.333
    # Weighted avg: (101.666 * 10 + 108.333 * 20) / 30 = (1016.66 + 2166.66) / 30 = 3183.33 / 30 = 106.111
    assert v[-1] > 106 and v[-1] < 107

def test_cvd_indicator_basic():
    candles = [
        Candle("1", 100, 110, 90, 102, 100),  # (102-90) - (110-102) = 12 - 8 = 4. Delta = 4/20 * 100 = 20
        Candle("2", 102, 105, 95, 100, 100),  # (100-95) - (105-100) = 5 - 5 = 0. Delta = 0
    ]
    cvd = cvd_indicator(candles)
    assert len(cvd) == 2
    assert cvd[0] == 20.0
    assert cvd[1] == 20.0

def test_detect_sweep_long():
    level = 100.0
    candles = [
        Candle("1", 110, 115, 105, 108, 10),
        Candle("2", 108, 110, 98, 99, 10),
        Candle("3", 99, 105, 99, 102, 10),
    ]
    assert detect_sweep(candles, level, "LONG") == True

def test_detect_sweep_short():
    level = 150.0
    candles = [
        Candle("1", 140, 145, 135, 142, 10),
        Candle("2", 142, 155, 142, 152, 10),
        Candle("3", 152, 152, 145, 148, 10),
    ]
    assert detect_sweep(candles, level, "SHORT") == True

def test_ema_filter_logic():
    # Price is 100, and we want to see if EMA200 works
    # Mocking simple candles to create an EMA
    candles = [Candle(str(i), 110, 115, 105, 110, 10) for i in range(250)]
    candles.append(Candle("last", 100, 101, 99, 100, 10))
    
    price = 100.0
    e200 = ema([c.close for c in candles], 200)
    assert e200 > 100.0  # EMA will be weighted towards 110
    
    cfg = {
        "pullback_ribbon": {"enabled": False},
        "sweep_invalidation": {
            "enabled": True,
            "ema_filter": True,
            "ema_period": 200,
            "eq_tolerance_pct": 0.0008,
            "vwap_target": False,
            "tp_r_mult": 2.0
        }
    }
    agent = SetupSignalAgent(cfg)
    state = State(candles=candles)
    state.market_context = {"price": price, "eq_low": 105.0} # Long setup
    state.cvd_divergence = {"divergence": "BULLISH"}
    
    state = agent.run(state)
    # Long blocked because Price (100) < EMA200 (~110)
    assert state.setup["name"] == "NONE"
    assert "ema_filter_blocked" in state.setup["reason"]

def test_vwap_target_logic():
    candles = [Candle(str(i), 100, 105, 95, 101, 10) for i in range(10)]
    v_last = vwap(candles)[-1]
    
    cfg = {
        "pullback_ribbon": {"enabled": False},
        "sweep_invalidation": {
            "enabled": True,
            "vwap_target": True,
            "ema_filter": False,
            "eq_tolerance_pct": 0.0008,
            "tp_r_mult": 2.0
        }
    }
    agent = SetupSignalAgent(cfg)
    state = State(candles=candles)
    state.market_context = {"price": 101.0, "eq_low": 100.0}
    state.cvd_divergence = {"divergence": "BULLISH"}
    
    state = agent.run(state)
    assert state.setup["side"] == "LONG"
    assert state.setup["tp"] == v_last
