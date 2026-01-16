from __future__ import annotations
from laptop_agents.core.logger import logger
from laptop_agents.core.registry import default_registry
from laptop_agents.memory.local_store import LocalMemoryStore


class Runner:
    def __init__(self, data_dir: str):
        self.registry = default_registry()
        self.memory = LocalMemoryStore(data_dir=data_dir, namespace="main")

    def run(self, agent_name: str, task: str) -> str:
        if agent_name not in self.registry:
            raise ValueError(f"Unknown agent '{agent_name}'. Available: {list(self.registry)}")

        self.memory.add("user", task, meta={"agent": agent_name})
        agent = self.registry[agent_name]
        res = agent.run(task)
        self.memory.add("agent", res.output, meta=res.meta)
        logger.info("Ran agent=%s", agent_name)
        return res.output
