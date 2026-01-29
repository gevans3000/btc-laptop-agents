from __future__ import annotations

import os
from typing import Any, Dict, Optional, Union

from laptop_agents.core.logger import logger
from laptop_agents.execution.bitunix_broker import BitunixBroker
from laptop_agents.paper.broker import PaperBroker
from laptop_agents.data.providers.bitunix_futures import BitunixFuturesProvider


def create_broker(
    execution_mode: str,
    symbol: str,
    starting_balance: float,
    fees_bps: float,
    slip_bps: float,
    state_path: str,
    strategy_config: Optional[Dict[str, Any]] = None,
) -> Union[PaperBroker, BitunixBroker]:
    """Factory to create the appropriate broker instance."""
    if execution_mode == "live":
        api_key = os.environ.get("BITUNIX_API_KEY")
        secret_key = os.environ.get("BITUNIX_API_SECRET") or os.environ.get(
            "BITUNIX_SECRET_KEY"
        )
        if not api_key or not secret_key:
            raise ValueError(
                "Live execution requires BITUNIX_API_KEY and BITUNIX_API_SECRET environment variables"
            )
        from laptop_agents.storage.trade_repository import TradeRepository

        repo = TradeRepository(state_path)

        live_provider = BitunixFuturesProvider(
            symbol=symbol, api_key=api_key, secret_key=secret_key
        )
        live_broker = BitunixBroker(
            live_provider, starting_equity=starting_balance, repo=repo
        )
        # Wire push notifications (Phase 1)
        live_provider.on_order_update = live_broker.on_order_update
        live_provider.on_position_update = live_broker.on_position_update

        logger.info(f"Initialized BitunixBroker with persistence at {state_path}")
        return live_broker
    else:
        # Paper mode
        paper_broker = PaperBroker(
            symbol=symbol,
            fees_bps=fees_bps,
            slip_bps=slip_bps,
            starting_equity=starting_balance,
            state_path=state_path,
            strategy_config=strategy_config,
        )
        logger.info(f"Initialized PaperBroker for {symbol}")
        return paper_broker
