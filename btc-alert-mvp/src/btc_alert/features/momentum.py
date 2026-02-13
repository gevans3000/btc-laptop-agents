from btc_alert.features.indicators import ema_momentum_signal


def compute_momentum(closes: list[float]) -> dict:
    score, regime = ema_momentum_signal(closes)
    return {"ema_momentum": score, "momentum_regime": regime}
