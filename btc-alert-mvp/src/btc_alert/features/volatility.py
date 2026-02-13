import statistics


def compute_volatility(closes: list[float], window: int = 20) -> dict:
    if len(closes) < window + 1:
        return {"volatility": 0.0}
    returns = []
    for i in range(-window, -1):
        prev_close = closes[i - 1]
        if prev_close == 0:
            continue
        returns.append((closes[i] - prev_close) / prev_close)
    vol = statistics.pstdev(returns) if returns else 0.0
    return {"volatility": vol}
