---
description: Execute tasks in fully autonomous "YOLO" mode
---

# YOLO Workflow (Autonomous Execution)

// turbo-all

1. Analyze the requested task and formulate a complete implementation plan.
2. Execute all code changes without waiting for individual approval.
3. Run all necessary terminal commands (tests, lint, build) with `SafeToAutoRun: true`.
4. Auto-commit and push changes upon successful verification.
5. Provide a summary report only after the entire task is complete or if an unrecoverable failure occurs.

## Usage
Run this workflow by instructing the agent: "Run /yolo to [task description]"
