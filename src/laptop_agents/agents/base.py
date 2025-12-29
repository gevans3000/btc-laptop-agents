from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol

@dataclass
class AgentResult:
    output: str
    meta: dict

class Agent(Protocol):
    name: str
    def run(self, task: str) -> AgentResult: ...
