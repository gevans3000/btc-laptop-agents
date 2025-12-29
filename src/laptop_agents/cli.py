from __future__ import annotations
import typer
from rich.console import Console
from dotenv import load_dotenv

from laptop_agents.core.logging import setup_logging
from laptop_agents.core.config import get_settings
from laptop_agents.core.runner import Runner

app = typer.Typer(add_completion=False)
console = Console()

@app.command()
def run(agent: str = typer.Option("planner", help="Agent name"),
        task: str = typer.Argument(..., help="Task text")):
    load_dotenv()
    setup_logging()
    settings = get_settings()
    runner = Runner(data_dir=settings.data_dir)
    out = runner.run(agent_name=agent, task=task)
    console.print(out)

@app.command()
def tail(n: int = typer.Option(20, help="Number of memory records to show")):
    load_dotenv()
    settings = get_settings()
    from laptop_agents.memory.local_store import LocalMemoryStore
    store = LocalMemoryStore(settings.data_dir, namespace="main")
    rows = store.tail(n=n)
    for r in rows:
        console.print(f"[{r.get('ts')}] {r.get('role')}: {r.get('content')[:200]}")

if __name__ == "__main__":
    app()
