import os
import logging

def setup_logging() -> None:
    level = os.getenv("LAPTOP_AGENTS_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
