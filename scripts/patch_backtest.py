import re
from pathlib import Path

p = Path("scripts/backtest_breakout_ema_atr.py")
t = p.read_text(encoding="utf-8")

# 1) Start loop later so warmup windows exist
t2, n1 = re.subn(
    r"for\s+i\s+in\s+range\(\s*1\s*,\s*len\(candles\)\s*-\s*1\s*\)\s*:",
    "start = max(args.donchian, args.ema, args.atr, 4)\n    for i in range(start, len(candles)-1):",
    t,
    count=1,
)

# 2) Guard Donchian lookback (prevents empty max())
t3, n2 = re.subn(
    r"lookback\s*=\s*candles\[i-args\.donchian:i\]\s*\n\s*hh\s*=\s*max\(x\.high\s+for\s+x\s+in\s+lookback\)",
    "lookback = candles[i-args.donchian:i]\n        if not lookback:\n            continue\n        hh = max(x.high for x in lookback)",
    t2,
    count=1,
)

p.write_text(t3, encoding="utf-8")
print(f"Patched {p} | loop_fix={n1} | lookback_guard={n2}")
