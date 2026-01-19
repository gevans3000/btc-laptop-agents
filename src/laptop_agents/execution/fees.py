from dataclasses import dataclass


@dataclass
class FeeTier:
    maker_bps: float
    taker_bps: float


# Bitunix standard tiers for futures
BITUNIX_DEFAULT_TIER = FeeTier(maker_bps=2.0, taker_bps=6.0)


def get_fee_bps(order_type: str, exchange: str = "bitunix") -> float:
    """Return fee in basis points based on order type and exchange."""
    # Basic modeling - can be expanded to multi-tier based on volume
    tier = BITUNIX_DEFAULT_TIER

    if order_type.upper() == "LIMIT":
        return tier.maker_bps
    else:  # MARKET
        return tier.taker_bps


def calculate_fee_amount(
    notional: float, order_type: str, exchange: str = "bitunix"
) -> float:
    bps = get_fee_bps(order_type, exchange)
    return notional * (bps / 10000.0)
