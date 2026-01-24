#!/usr/bin/env python3
"""
BTC Laptop Agents: Autonomous Development Harness
=================================================
This script runs a full system diagnostic and generates a report designed
specifically for AI/LLM debugging.

Usage:
    python scripts/test_everything.py

Instructions:
    1. Run this script.
    2. Wait for it to finish (approx 1-2 mins).
    3. Copy the text between "BEGIN REPORT" and "END REPORT".
    4. Paste it into your AI chat window to get instant fixes.
"""

import sys
import subprocess
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

# --- Configuration ---
REPO_ROOT = Path(__file__).resolve().parent.parent


def print_header(title: str, char="="):
    print(f"\n{char * 60}")
    print(f" {title}")
    print(f"{char * 60}")


def run_step(
    name: str, cmd: List[str], cwd: Path = REPO_ROOT, timeout: int = 180
) -> Dict[str, Any]:
    """Runs a verification step and captures the output."""
    print(f"Running {name}...", end="", flush=True)
    start_time = time.time()

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        duration = time.time() - start_time
        success = result.returncode == 0

        status = "PASS" if success else "FAIL"
        # Optional: Add colors for local terminal (PowerShell supports these)
        color_code = "\033[92m" if success else "\033[91m"
        reset_code = "\033[0m"

        print(f" [{color_code}{status}{reset_code}] ({duration:.2f}s)")

        return {
            "name": name,
            "success": success,
            "cmd": " ".join(cmd),
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration": duration,
            "returncode": result.returncode,
        }
    except Exception as e:
        print(" [\033[91mERROR\033[0m]")
        return {
            "name": name,
            "success": False,
            "cmd": " ".join(cmd),
            "stdout": "",
            "stderr": str(e),
            "duration": time.time() - start_time,
            "returncode": -1,
        }


def generate_report(results: List[Dict[str, Any]]) -> str:
    """Generates the Markdown report for the LLM."""
    md = []
    timestamp = datetime.now().isoformat()
    overall_status = (
        "HEALTHY" if all(r["success"] for r in results) else "NEEDS ATTENTION"
    )

    md.append("# System Diagnostic Report")
    md.append(f"**Timestamp**: {timestamp}")
    md.append(f"**Overall Status**: {overall_status}")
    md.append("")

    md.append("## Executive Summary")
    for r in results:
        icon = "✅" if r["success"] else "❌"
        md.append(
            f"- {icon} **{r['name']}**: {'Pass' if r['success'] else 'Fail'} ({r['duration']:.2f}s)"
        )

    md.append("")
    md.append("## Detailed Failures")

    failures_found = False
    for r in results:
        if not r["success"]:
            failures_found = True
            md.append(f"### 🔴 {r['name']}")
            md.append(f"**Command**: `{r['cmd']}`")
            md.append(f"**Exit Code**: {r['returncode']}")
            md.append("#### Output Trace")
            md.append("```text")

            content = r["stderr"].strip()
            if not content:
                content = r["stdout"].strip()
            if not content:
                content = "<No Output Captured>"

            lines = content.splitlines()
            if len(lines) > 150:
                md.append(f"... (truncating {len(lines) - 150} lines) ...")
                md.append("\n".join(lines[-150:]))
            else:
                md.append(content)

            md.append("```")
            md.append("---")

    if not failures_found:
        md.append("No failures detected. The system appears stable.")

    return "\n".join(md)


def main():
    print_header("BTC LAPTOP AGENTS: DIAGNOSTIC HARNESS")

    python_exe = sys.executable
    results = []

    # Define steps
    steps = [
        ("System Doctor", [python_exe, "-m", "laptop_agents", "doctor"]),
        (
            "Unit Tests",
            [
                python_exe,
                "-m",
                "pytest",
                "tests",
                "-v",
                "--tb=short",
                "-p",
                "no:cacheprovider",
            ],
        ),
        (
            "Type Safety",
            [python_exe, "-m", "mypy", "src/laptop_agents", "--ignore-missing-imports"],
        ),
        (
            "Backtest Sim",
            [
                python_exe,
                "-m",
                "laptop_agents",
                "run",
                "--mode",
                "backtest",
                "--symbol",
                "BTCUSDT",
                "--backtest",
                "500",
                "--risk-pct",
                "0.1",
                "--quiet",
            ],
        ),
    ]

    for name, cmd in steps:
        results.append(run_step(name, cmd))

    report_text = generate_report(results)

    separator = "=" * 60
    print(f"\n\n{separator}")
    print(" 👇 COPY THE TEXT BELOW AND PASTE IT INTO CHAT 👇")
    print(separator)
    print(f"\n{report_text}\n")
    print(separator)
    print(" 👆 END OF REPORT 👆")
    print(f"{separator}\n")

    if all(r["success"] for r in results):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
