from __future__ import annotations
from typing import Protocol, List, Union, AsyncGenerator, runtime_checkable
from laptop_agents.trading.helpers import Candle, Tick, DataEvent


@runtime_checkable
class Provider(Protocol):
    """Protocol defining the interface for an exchange provider."""

    def listen(self) -> AsyncGenerator[Union[Candle, Tick, DataEvent], None]:
        """Provides a stream of market data."""
        ...

    def history(self, n: int = 200) -> List[Candle]:
        """Returns n historical candles."""
        ...
