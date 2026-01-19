from __future__ import annotations
from dataclasses import dataclass
from .base import AgentResult


@dataclass
class PlannerAgent:
    name: str = "planner"

    def run(self, task: str) -> AgentResult:
        plan = [
            "1) Restate objective in one sentence.",
            "2) List required inputs/files.",
            "3) Produce smallest viable output.",
            "4) Add automation script if repetitive.",
        ]
        return AgentResult(
            output=f"PLAN for: {task}\n" + "\n".join(plan),
            meta={"type": "plan"},
        )
