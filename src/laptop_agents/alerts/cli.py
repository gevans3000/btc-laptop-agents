"""CLI entry point for the BTC alert system."""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional


def alert(
    config: str = "",
    once: bool = False,
    verbose: bool = False,
) -> None:
    """Run the BTC alert pipeline.

    Args:
        config: Path to alerts.yaml config file.
        once: Run a single cycle then exit.
        verbose: Enable debug logging.
    """
    # Configure logging
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    from laptop_agents.alerts.pipeline import run_loop

    # Resolve config path
    config_path: Optional[str] = None
    if config:
        config_path = config
    else:
        # Try default locations
        candidates = [
            os.path.join(os.getcwd(), "config", "alerts.yaml"),
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "config", "alerts.yaml"),
        ]
        for c in candidates:
            if os.path.exists(c):
                config_path = c
                break

    max_iter = 1 if once else 0
    try:
        run_loop(config_path=config_path, max_iterations=max_iter)
    except KeyboardInterrupt:
        print("\n🛑 Alert loop stopped by user.")
        sys.exit(0)
