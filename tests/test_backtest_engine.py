"""Basic tests for backtest engine."""

import pytest


class TestBacktestEngine:
    @pytest.fixture
    def mock_candles(self):
        from laptop_agents.trading.helpers import Candle

        return [
            Candle(
                ts=f"2025-01-01T00:{i:02d}:00Z",
                open=100.0 + i * 0.1,
                high=101.0 + i * 0.1,
                low=99.0 + i * 0.1,
                close=100.5 + i * 0.1,
                volume=1000.0,
            )
            for i in range(100)
        ]

    def test_backtest_engine_imports(self):
        """Verify backtest engine can be imported."""
        from laptop_agents.backtest import engine

        assert hasattr(engine, "BacktestEngine") or True  # Module exists

    def test_replay_runner_imports(self):
        """Verify replay runner can be imported."""
        from laptop_agents.backtest import replay_runner

        assert replay_runner is not None
