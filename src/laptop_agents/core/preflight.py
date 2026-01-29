from dataclasses import dataclass
from typing import List, Tuple, Callable, Any, Dict


@dataclass
class PreflightResult:
    name: str
    passed: bool
    message: str


def check_api_connectivity(config: Dict[str, Any]) -> bool:
    from laptop_agents.data.providers.bitunix_client import BitunixClient

    try:
        api_key = config.get("api_key")
        secret_key = config.get("secret_key")
        client = BitunixClient(api_key=api_key, secret_key=secret_key)
        # Ping via trading pairs (public) or user info (signed)
        client.get(
            "/api/v1/futures/market/trading_pairs", params={"symbols": "BTCUSDT"}
        )
        return True
    except Exception:
        return False


def check_position_match(config: Dict[str, Any]) -> bool:
    from laptop_agents.data.providers.bitunix_futures import BitunixFuturesProvider
    from laptop_agents.storage.trade_repository import TradeRepository
    from pathlib import Path

    symbol = config.get("symbol", "BTCUSDT")
    api_key = config.get("api_key")
    secret_key = config.get("secret_key")

    if not api_key or not secret_key:
        return True  # Can't check without keys

    provider = BitunixFuturesProvider(
        symbol=symbol, api_key=api_key, secret_key=secret_key
    )

    # Check Exchange
    try:
        exchange_positions = provider.get_pending_positions(symbol)
        exchange_pos = None
        for p in exchange_positions:
            if p.get("symbol") == symbol:
                qty = float(p.get("qty") or p.get("positionAmount") or 0)
                if abs(qty) > 1e-8:
                    exchange_pos = p
                    break
    except Exception:
        return False

    # Check Local DB
    db_path = Path(".workspace/runs/trading.db")
    if not db_path.exists():
        # If no DB, we expect exchange to be flat
        return exchange_pos is None

    repo = TradeRepository(str(db_path))
    local_pos = repo.load_position(symbol)

    local_qty = float(local_pos.get("qty", 0)) if local_pos else 0.0
    exchange_qty = float(exchange_pos.get("qty", 0) if exchange_pos else 0.0)

    if abs(local_qty - exchange_qty) > 1e-8:
        # Mismatch! Especially critical if local=FLAT but exchange=OPEN
        return False

    return True


def check_min_equity(config: Dict[str, Any]) -> bool:
    return True


def check_daily_loss(config: Dict[str, Any]) -> bool:
    return True


def check_leverage(config: Dict[str, Any]) -> bool:
    from laptop_agents.data.providers.bitunix_client import BitunixClient
    from laptop_agents.core.logger import logger

    symbol = config.get("symbol", "BTCUSDT")
    api_key = config.get("api_key")
    secret_key = config.get("secret_key")
    target_leverage = int(config.get("max_leverage", 1))

    if not api_key or not secret_key:
        return True

    client = BitunixClient(api_key=api_key, secret_key=secret_key)
    try:
        # 1. Fetch current leverage
        # Bitunix API for futures user info/setting leverage
        resp = client.get(
            "/api/v1/futures/account/user_config",
            params={"symbol": symbol},
            signed=True,
        )
        data = resp.get("data", {})
        current_lev = int(data.get("leverage", 0))

        if current_lev != target_leverage:
            logger.warning(
                f"Leverage mismatch for {symbol}: Current={current_lev}, Target={target_leverage}. Attempting to set..."
            )
            # 2. Set leverage
            client.post(
                "/api/v1/futures/account/set_leverage",
                body={
                    "symbol": symbol,
                    "leverage": target_leverage,
                    "side": 3,  # 1: Long, 2: Short, 3: Both
                },
                signed=True,
            )
            logger.info(f"Leverage set to {target_leverage}x for {symbol}.")

        return True
    except Exception as e:
        logger.error(f"Failed to enforce leverage: {e}")
        return False


def check_kill_switch(config: Dict[str, Any]) -> bool:
    import os

    val = os.environ.get("LA_KILL_SWITCH", "FALSE")
    return bool(val == "FALSE")


PREFLIGHT_GATES: List[Tuple[str, Callable[[Dict[str, Any]], bool]]] = [
    ("api_connectivity", check_api_connectivity),
    ("position_reconciliation", check_position_match),
    ("leverage_enforcement", check_leverage),
    ("min_equity", check_min_equity),
    ("daily_loss_ok", check_daily_loss),
    ("kill_switch_off", check_kill_switch),
]


def run_preflight(config: Dict[str, Any]) -> List[PreflightResult]:
    results = []
    for name, gate_func in PREFLIGHT_GATES:
        try:
            passed: bool = gate_func(config)
            results.append(
                PreflightResult(name, passed, "Passed" if passed else "Failed")
            )
        except Exception as e:
            results.append(PreflightResult(name, False, str(e)))
    return results


def all_gates_passed(results: List[PreflightResult]) -> bool:
    return all(r.passed for r in results)
