from __future__ import annotations
from laptop_agents.agents.planner import PlannerAgent
from laptop_agents.agents.researcher import ResearcherAgent

def default_registry():
    return {
        "planner": PlannerAgent(),
        "researcher": ResearcherAgent(),
    }
