from __future__ import annotations
import pandas as pd
from pathlib import Path
from typing import Dict, Optional, Union
from laptop_agents.core.logger import logger


class FundingLoader:
    """Loads historical funding rates and provides the rate for a given timestamp."""

    def __init__(self, csv_path: Union[str, Path]):
        self.csv_path = Path(csv_path)
        self.rates: Dict[str, float] = {}
        self._load()

    def _load(self) -> None:
        if not self.csv_path.exists():
            logger.warning(f"Funding data not found at {self.csv_path}")
            return

        df = pd.read_csv(self.csv_path)
        # Expecting 'ts' and 'rate' columns
        df.columns = [c.lower() for c in df.columns]
        for _, row in df.iterrows():
            self.rates[str(row.ts)] = float(row.rate)
        logger.info(f"Loaded {len(self.rates)} funding rates")

    def get_rate_at(self, ts: str) -> Optional[float]:
        """Return funding rate if exactly at a timestamp or matched in data.
        In a real scenario, this would check 8h boundaries.
        """
        return self.rates.get(ts)
