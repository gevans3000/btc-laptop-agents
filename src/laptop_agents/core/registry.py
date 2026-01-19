from __future__ import annotations
from laptop_agents.agents.planner import PlannerAgent
from laptop_agents.agents.researcher import ResearcherAgent


def default_registry():
    """Registry for simple CLI agents (planner/researcher).
    For full 5-agent trading stack, use Supervisor directly.
    """
    return {
        "planner": PlannerAgent(),
        "researcher": ResearcherAgent(),
    }
