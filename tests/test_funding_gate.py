import unittest
from laptop_agents.agents.derivatives_flows import DerivativesFlowsAgent
from laptop_agents.agents.state import State


class TestFundingGate(unittest.TestCase):
    def test_extreme_funding_halts(self):
        class MockProvider:
            def snapshot_derivatives(self):
                return {"funding_8h": 0.002}  # 0.2% - extreme

        gates = {
            "no_trade_funding_8h": 0.0005,
            "half_size_funding_8h": 0.0002,
            "extreme_funding_8h": 0.001,
        }
        agent = DerivativesFlowsAgent(MockProvider(), gates)

        state = State(instrument="BTCUSDT", timeframe="1m")
        state = agent.run(state)

        self.assertIn("HALT_funding_extreme", state.derivatives["flags"])

    def test_normal_funding_passes(self):
        class MockProvider:
            def snapshot_derivatives(self):
                return {"funding_8h": 0.0001}  # Normal

        gates = {
            "no_trade_funding_8h": 0.0005,
            "half_size_funding_8h": 0.0002,
            "extreme_funding_8h": 0.001,
        }
        agent = DerivativesFlowsAgent(MockProvider(), gates)

        state = State(instrument="BTCUSDT", timeframe="1m")
        state = agent.run(state)

        self.assertEqual(state.derivatives["flags"], [])


if __name__ == "__main__":
    unittest.main()
