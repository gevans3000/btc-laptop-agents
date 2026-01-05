from __future__ import annotations
from dataclasses import dataclass
from .base import AgentResult

@dataclass
class ResearcherAgent:
    name: str = "researcher"

    def run(self, task: str) -> AgentResult:
        return AgentResult(
            output=f"OFFLINE RESEARCH NOTE:\n- Offline mode.\n- Task received: {task}\n- Next: enable tools.web or add API integration.",
            meta={"type": "note", "mode": "offline"},
        )
