"""Verify broker implementations satisfy BrokerProtocol."""

from laptop_agents.core.protocols import BrokerProtocol


class TestProtocolCompliance:
    def test_paper_broker_implements_protocol(self):
        from laptop_agents.paper.broker import PaperBroker

        broker = PaperBroker(symbol="BTCUSDT")
        assert isinstance(broker, BrokerProtocol)

    def test_dry_run_broker_implements_protocol(self):
        from laptop_agents.core.orchestrator import DryRunBroker

        broker = DryRunBroker(symbol="BTCUSDT")
        assert isinstance(broker, BrokerProtocol)
