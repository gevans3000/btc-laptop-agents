#!/usr/bin/env python3
"""
Test Harness for Continuous Autonomous Development
==================================================
This script serves as the "Controller" for the autonomous development loop.
It runs a comprehensive battery of tests and system checks, generating a
machine-readable status report that an LLM agent can use to determine the next fix.

Usage:
    python scripts/harness.py

Output:
    - Console summary
    - .workspace/harness_report.json (Machine readable)
    - .workspace/harness_context.md (LLM prompt context)
"""

import sys
import json
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

# --- Configuration ---
REPO_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = REPO_ROOT / ".workspace"
REPORT_JSON = WORKSPACE / "harness_report.json"
REPORT_MD = WORKSPACE / "harness_context.md"


def print_header(title: str):
    print(f"\n{'=' * 60}")
    print(f" {title}")
    print(f"{'=' * 60}")


def run_command(
    cmd: List[str], cwd: Path = REPO_ROOT, capture_output=True
) -> Dict[str, Any]:
    """Run a subprocess command and return result dict."""
    start_time = time.time()
    try:
        print(f"Running: {' '.join(cmd)} ... ", end="", flush=True)
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=capture_output, text=True, timeout=300
        )
        duration = time.time() - start_time
        success = result.returncode == 0
        status_str = "PASS" if success else "FAIL"
        print(f"[{status_str}] ({duration:.2f}s)")

        return {
            "command": " ".join(cmd),
            "success": success,
            "returncode": result.returncode,
            "stdout": result.stdout[:5000],  # Truncate
            "stderr": result.stderr[:5000],  # Truncate
            "duration": duration,
        }
    except Exception as e:
        print(f"[ERROR] {e}")
        return {
            "command": " ".join(cmd),
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": str(e),
            "duration": time.time() - start_time,
        }


def generate_llm_context(report: Dict[str, Any]):
    """Generate a Markdown file optimized for LLM reading."""
    md = [
        f"# System Status Report ({report['timestamp']})",
        "",
        "## Executive Summary",
        f"- **Overall Status**: {'PASS' if report['overall_success'] else 'FAIL'}",
        f"- **Tests Run**: {report['stats']['total_steps']}",
        f"- **Failed**: {report['stats']['failures']}",
        "",
        "## Detailed Step Results",
    ]

    for step in report["steps"]:
        icon = "✅" if step["success"] else "❌"
        md.append(f"### {icon} {step['name']}")
        md.append(f"- **Command**: `{step['result']['command']}`")
        md.append(f"- **Duration**: {step['result']['duration']:.2f}s")
        if not step["success"]:
            md.append("\n**STDERR Output**:")
            md.append("```text")
            md.append(
                step["result"]["stderr"].strip()
                or step["result"]["stdout"].strip()
                or "No output"
            )
            md.append("```")
        md.append("")

    md.append("## Recommended Actions")
    if report["overall_success"]:
        md.append(
            "System is healthy. Proceed with feature development or optimization."
        )
    else:
        md.append("Fix the errors listed above in priority order:")
        md.append("1. Static Analysis / Syntax errors")
        md.append("2. Unit Test failures")
        md.append("3. Runtime/Integration failures")

    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"\nGenerated LLM Context: {REPORT_MD}")


def main():
    WORKSPACE.mkdir(exist_ok=True)
    report = {
        "timestamp": datetime.now().isoformat(),
        "steps": [],
        "overall_success": True,
        "stats": {"total_steps": 0, "failures": 0},
    }

    print_header("AUTOMATED DEVELOPMENT HARNESS")

    # 1. Doctor / Environment (Static)
    step_doc = run_command([sys.executable, "-m", "laptop_agents", "doctor"])
    report["steps"].append(
        {"name": "System Doctor", "result": step_doc, "success": step_doc["success"]}
    )

    # 2. Unit Tests (Logic)
    # Using python -m pytest to ensure path correctness
    step_test = run_command(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests",
            "-v",
            "--tb=short",
            "-p",
            "no:cacheprovider",
        ]
    )
    report["steps"].append(
        {"name": "Unit Tests", "result": step_test, "success": step_test["success"]}
    )

    # 3. Code Verification (Mypy - Optional if installed)
    # We check if mypy is available first
    try:
        subprocess.run([sys.executable, "-m", "mypy", "--version"], capture_output=True)
        step_type = run_command(
            [
                sys.executable,
                "-m",
                "mypy",
                "src/laptop_agents",
                "--ignore-missing-imports",
            ]
        )
        report["steps"].append(
            {"name": "Type Check", "result": step_type, "success": step_type["success"]}
        )
    except FileNotFoundError:
        print("Skipping Type Check (mypy not found)")

    # 4. Simulation / Integration (Engine)
    # We run a tiny backtest to verify the engine loads and runs
    step_sim = run_command(
        [
            sys.executable,
            "-m",
            "laptop_agents",
            "run",
            "--mode",
            "backtest",
            "--symbol",
            "BTCUSDT",
            "--backtest",
            "1000",
            "--risk-pct",
            "0.1",
            "--quiet",
        ]
    )
    # Note: If backtest opens a browser, this might hang on headless.
    # Assuming base backtest is console-only or safe.
    report["steps"].append(
        {
            "name": "Engine Simulation",
            "result": step_sim,
            "success": step_sim["success"],
        }
    )

    # Final Stats
    failures = [s for s in report["steps"] if not s["success"]]
    report["overall_success"] = len(failures) == 0
    report["stats"]["total_steps"] = len(report["steps"])
    report["stats"]["failures"] = len(failures)

    # Save Report
    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    generate_llm_context(report)

    if not report["overall_success"]:
        print_header("⚠️  SYSTEM VERIFICATION FAILED ⚠️")
        print(f"Failed Steps: {', '.join([s['name'] for s in failures])}")
        sys.exit(1)
    else:
        print_header("✅  ALL SYSTEMS GO ✅")
        sys.exit(0)


if __name__ == "__main__":
    main()
