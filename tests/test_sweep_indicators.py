import pytest
from laptop_agents.indicators import Candle, vwap, detect_sweep, cvd_indicator, ema
from laptop_agents.agents.cvd_divergence import CvdDivergenceAgent
from laptop_agents.agents.state import State
from laptop_agents.agents.setup_signal import SetupSignalAgent

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

def test_detect_sweep_long_reclaim():
    window = [Candle(str(i), 100, 101, 95, 100, 100) for i in range(10)]
    curr = Candle("curr", 96, 97, 94, 96, 100)  # wick below 95, close above
    result = detect_sweep(window + [curr], lookback=10)
    assert result["swept"] == "LOW"
    assert result["reclaimed"] is True
    assert result["level"] == 95


def test_detect_sweep_high_reclaim():
    window = [Candle(str(i), 100, 105, 99, 100, 100) for i in range(10)]
    curr = Candle("curr", 104, 106, 103, 104, 100)  # wick above 105, close below
    result = detect_sweep(window + [curr], lookback=10)
    assert result["swept"] == "HIGH"
    assert result["reclaimed"] is True


def test_detect_sweep_none():
    window = [Candle(str(i), 100, 105, 95, 100, 100) for i in range(10)]
    curr = Candle("curr", 100, 104, 96, 101, 100)  # no sweep
    result = detect_sweep(window + [curr], lookback=10)
    assert result["swept"] is None
    assert result["reclaimed"] is False

def test_ema_filter_logic():
    # Price is 100, and we want to see if EMA200 works
    # Mocking simple candles to create an EMA
    candles = [Candle(str(i), 110, 115, 105, 110, 10) for i in range(250)]
    # Sweep 105 level, reclaimed at 106. Price (106) < EMA (110) => trend_down
    candles.append(Candle("last", 104, 107, 103, 106, 100))
    
    price = 106.0
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
    # 10 candles for window, plus 1 for 'current' sweep
    candles = [Candle(str(i), 101, 105, 100, 101, 10) for i in range(10)]
    # Current sweeps 100 (low 98) and reclaims (close 102)
    candles.append(Candle("curr", 100, 103, 98, 102, 10))
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
    state.market_context = {"price": 102.0}
    state.cvd_divergence = {"divergence": "BULLISH"}
    
    state = agent.run(state)
    assert state.setup["side"] == "LONG"
    assert state.setup["tp"] == v_last
