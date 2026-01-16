from __future__ import annotations
from laptop_agents.agents.planner import PlannerAgent
from laptop_agents.agents.researcher import ResearcherAgent
from laptop_agents.agents.supervisor import Supervisor
from laptop_agents.agents.state import State

def default_registry():
    """Registry for simple CLI agents (planner/researcher).
    For full 5-agent trading stack, use Supervisor directly.
    """
    return {
        "planner": PlannerAgent(),
        "researcher": ResearcherAgent(),
    }
