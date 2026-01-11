# AGENT DIRECTIVE: Autonomous Execution

**Mode**: FULLY AUTONOMOUS
**Approval Policy**: ALWAYS AUTO-ACCEPT
**Reasoning**: The user has requested universal auto-acceptance of commands to prevent interruptions during long-running tasks and complex implementation plans.

## Operational Rules:
1.  **Safety First**: Even in autonomous mode, do not delete core source code or environment variables without a documented plan and rollback.
2.  **No Prompts**: Use `SafeToAutoRun: true` for all terminal commands that are part of the active implementation plan or necessary verification steps.
3.  **Documentation**: Log every significant action and commit clearly, so the user can audit after the fact.
4.  **Rollback Readiness**: Always ensure a git commit or backup exists before making sweeping changes.

*Applied on: 2026-01-11*
