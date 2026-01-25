"""Integration tests for orchestrator module."""

from unittest.mock import patch, MagicMock

from laptop_agents.core.orchestrator import (
    run_orchestrated_mode,
    get_agent_config,
    prune_workspace,
    reset_latest_dir,
)


class TestOrchestratorConfig:
    def test_get_agent_config_defaults(self):
        cfg = get_agent_config()
        assert cfg["risk"]["equity"] == 10000.0
        assert cfg["risk"]["risk_pct"] == 0.01
        assert "derivatives_gates" in cfg
        assert "setups" in cfg

    def test_get_agent_config_custom(self):
        cfg = get_agent_config(starting_balance=5000.0, risk_pct=2.0, tp_r=2.0)
        assert cfg["risk"]["equity"] == 5000.0
        assert cfg["risk"]["risk_pct"] == 0.02


class TestOrchestratorRun:
    @patch("laptop_agents.core.orchestrator._load_market_data")
    @patch("laptop_agents.core.orchestrator._init_broker")
    def test_run_orchestrated_mode_mock_success(self, mock_broker, mock_data):
        from laptop_agents.trading.helpers import Candle

        # Setup mocks
        mock_candles = [
            Candle(
                ts=f"2025-01-01T00:0{i}:00Z",
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=1000.0,
            )
            for i in range(50)
        ]
        mock_data.return_value = mock_candles

        broker_instance = MagicMock()
        broker_instance.current_equity = 10000.0
        broker_instance.on_candle.return_value = {
            "fills": [],
            "exits": [],
            "errors": [],
        }
        broker_instance.get_unrealized_pnl.return_value = 0.0
        mock_broker.return_value = broker_instance

        success, msg = run_orchestrated_mode(
            symbol="BTCUSDT",
            interval="1m",
            source="mock",
            limit=50,
            fees_bps=2.0,
            slip_bps=0.5,
        )

        assert success is True
        assert "Run ID" in msg


class TestWorkspacePruning:
    @patch("laptop_agents.core.orchestrator.Path")
    def test_prune_workspace_no_runs(self, mock_path):
        # Setup mock to simulate non-existent directory
        mock_runs_dir = MagicMock()
        mock_runs_dir.exists.return_value = False

        with patch("laptop_agents.core.orchestrator.RUNS_DIR", mock_runs_dir):
            prune_workspace(keep=5)
            # Should not raise

    @patch("laptop_agents.core.orchestrator.shutil")
    @patch("laptop_agents.core.orchestrator.Path")
    def test_reset_latest_dir(self, mock_path, mock_shutil):
        # Simulate LATEST_DIR exists and needs removal
        mock_latest = MagicMock()
        mock_latest.exists.return_value = True

        with patch("laptop_agents.core.orchestrator.LATEST_DIR", mock_latest):
            reset_latest_dir()

            # Verify cleanup and recreation
            mock_shutil.rmtree.assert_called_once()
            mock_latest.mkdir.assert_called_once()
