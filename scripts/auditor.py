import sys
import subprocess
import typer
from pathlib import Path
from rich.console import Console

console = Console()
app = typer.Typer()

REPO_ROOT = Path(__file__).parent.parent


@app.command()
def check():
    """Check running agent health."""
    console.print("[bold blue]Auditing Agent Health...[/bold blue]")
    try:
        subprocess.run(
            [sys.executable, "-m", "laptop_agents", "verify-agent-health"], check=True
        )
    except subprocess.CalledProcessError:
        console.print("[red]Agent appears to be STUCK or NOT RUNNING.[/red]")
        sys.exit(1)


@app.command()
def diff(
    commits: int = typer.Option(1, help="Number of commits to audit"),
    preview: bool = typer.Option(False, help="Show diff in console"),
):
    """Get the diff of recent changes for auditing."""
    console.print(
        f"[bold blue]Collecting Diff (Last {commits} commits + Unstaged)...[/bold blue]"
    )

    # 1. Unstaged changes
    unstaged = subprocess.check_output(["git", "diff"], encoding="utf-8")

    # 2. Staged but not committed
    staged = subprocess.check_output(["git", "diff", "--cached"], encoding="utf-8")

    # 3. Last N commits
    recent = subprocess.check_output(
        ["git", "show", f"HEAD~{commits}..HEAD"], encoding="utf-8"
    )

    full_report = f"# Audit Report\n\n## Unstaged Changes\n{unstaged}\n\n## Staged Changes\n{staged}\n\n## Recent Commits\n{recent}"

    if preview:
        console.print(full_report)

    # Save to file for AI to read
    report_path = REPO_ROOT / ".workspace" / "audit_diff.txt"
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(full_report, encoding="utf-8")
    console.print(f"[green]Audit diff saved to {report_path}[/green]")


@app.command()
def scan():
    """Scan for common implementation bugs (debug prints, TODOs)."""
    console.print("[bold blue]Scanning for Leftover Artifacts...[/bold blue]")
    try:
        # Grep for print() statements in src/
        res = subprocess.run(
            ["grep", "-r", "print(", "src/"], capture_output=True, text=True
        )
        if res.stdout:
            console.print(
                "[yellow]Found 'print()' statements (Use logger instead):[/yellow]"
            )
            console.print(res.stdout)

        # Grep for USER_TODO
        res = subprocess.run(
            ["grep", "-r", "USER_TODO", "src/"], capture_output=True, text=True
        )
        if res.stdout:
            console.print("[yellow]Found 'USER_TODO':[/yellow]")
            console.print(res.stdout)

    except FileNotFoundError:
        console.print("[yellow]grep not found, skipping scan.[/yellow]")


if __name__ == "__main__":
    app()
