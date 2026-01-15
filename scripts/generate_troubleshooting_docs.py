"""
Generate Troubleshooting Documentation from the Agent's Knowledge Base.

Usage:
    python scripts/generate_troubleshooting_docs.py
"""
import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
MEMORY_FILE = PROJECT_ROOT / ".agent/memory/known_errors.jsonl"
OUTPUT_FILE = PROJECT_ROOT / "docs/troubleshooting/known_issues.md"

def load_memory() -> list:
    """Load all known errors from memory."""
    if not MEMORY_FILE.exists():
        return []
    entries = []
    try:
        content = MEMORY_FILE.read_text(encoding='utf-8').strip()
        if not content:
            return []
        for line in content.split('\n'):
            if line and not line.startswith('{"_meta"'):
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except Exception as e:
        print(f"Error loading memory: {e}")
    return entries

def generate_markdown(entries: list) -> str:
    """Generate Markdown content for the troubleshooting guide."""
    
    # Filter for entries that have a solution
    solved = [e for e in entries if e.get("solution") and e.get("solution") not in ["NEEDS_DIAGNOSIS", "Pending Diagnosis", ""]]
    
    md = [
        "# Automated Troubleshooting Guide",
        "",
        "> **Note**: This document is auto-generated from the Agent's Learning Debugger knowledge base.",
        f"> **Last Updated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Table of Contents",
        ""
    ]
    
    if not solved:
        md.append("_No known issues with solutions recorded yet._")
        return "\n".join(md)
    
    # Generate TOC
    for i, entry in enumerate(solved, 1):
        fingerprint = entry.get('fingerprint', 'unknown')
        # Create anchor from fingerprint (assuming it's safe chars)
        md.append(f"{i}. [{fingerprint}](#issue-{fingerprint})")
        
    md.append("")
    md.append("---")
    md.append("")
    
    # Generate Details
    for entry in solved:
        fingerprint = entry.get('fingerprint', 'unknown')
        snippet = entry.get('error_snippet', 'N/A')
        solution = entry.get('solution', 'N/A')
        root_cause = entry.get('root_cause', 'N/A')
        occurrences = entry.get('occurrences', 1)
        last_seen = entry.get('last_seen', 'N/A')
        
        md.append(f"## Issue: {fingerprint} <a id='issue-{fingerprint}'></a>")
        md.append("")
        md.append(f"**Last Seen**: {last_seen} | **Occurrences**: {occurrences}")
        md.append("")
        md.append("### Error Signature")
        md.append("```text")
        # Truncate snippet if too long
        md.append(snippet[:500] + ("..." if len(snippet) > 500 else ""))
        md.append("```")
        md.append("")
        md.append("### Root Cause")
        md.append(root_cause if root_cause else "_Not documented._")
        md.append("")
        md.append("### Solution")
        md.append(f"> {solution}")
        md.append("")
        md.append("---")
        md.append("")
        
    return "\n".join(md)

def main():
    entries = load_memory()
    print(f"Loaded {len(entries)} entries from memory.")
    
    content = generate_markdown(entries)
    
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(content, encoding='utf-8')
    print(f"✓ Troubleshooting guide generated at: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
