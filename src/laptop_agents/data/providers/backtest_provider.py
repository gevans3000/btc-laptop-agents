from __future__ import annotations
import pandas as pd
from pathlib import Path
from typing import List, AsyncGenerator, Union, Optional
from laptop_agents.trading.helpers import Candle
from laptop_agents.core.logger import logger


class BacktestProvider:
    """Historical data provider for backtesting.
    Loads data from CSV or Parquet and yields candles.
    """

    def __init__(self, data_path: Union[str, Path], symbol: str = "BTCUSDT"):
        self.data_path = Path(data_path)
        self.symbol = symbol
        self._df: Optional[pd.DataFrame] = None
        self._load_data()

    def _load_data(self) -> None:
        if not self.data_path.exists():
            # If path is a directory, look for latest parquet/csv
            if self.data_path.is_dir():
                files = list(self.data_path.glob("*.parquet")) + list(
                    self.data_path.glob("*.csv")
                )
                if not files:
                    logger.warning(f"No data files found in {self.data_path}")
                    self._df = pd.DataFrame(
                        columns=["ts", "open", "high", "low", "close", "volume"]
                    )
                    return
                self.data_path = max(files, key=lambda p: p.stat().st_mtime)

        logger.info(f"Loading backtest data from {self.data_path}")
        if self.data_path.suffix == ".parquet":
            self._df = pd.read_parquet(self.data_path)
        else:
            self._df = pd.read_csv(self.data_path)

        # Standardize columns
        self._df.columns = [c.lower() for c in self._df.columns]
        if "timestamp" in self._df.columns and "ts" not in self._df.columns:
            self._df.rename(columns={"timestamp": "ts"}, inplace=True)

        # Ensure ts is string for Candle compat
        self._df["ts"] = self._df["ts"].astype(str)
        logger.info(f"Loaded {len(self._df)} candles for {self.symbol}")

    def history(self, n: int = 200) -> List[Candle]:
        """Return first n candles for warmup."""
        if self._df is None or self._df.empty:
            return []

        warmup = self._df.head(n)
        return [
            Candle(
                ts=row.ts,
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
            )
            for _, row in warmup.iterrows()
        ]

    async def listen(self, start_after: int = 200) -> AsyncGenerator[Candle, None]:
        """Yield candles one by one (after warmup)."""
        if self._df is None or self._df.empty:
            return

        remaining = self._df.iloc[start_after:]
        for _, row in remaining.iterrows():
            yield Candle(
                ts=row.ts,
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
            )

    def get_instrument_info(self, symbol: str) -> dict:
        """Return tick size, lot size, etc."""
        return {
            "symbol": symbol,
            "tick_size": 0.1,
            "lot_size": 0.001,
            "min_qty": 0.001,
        }
