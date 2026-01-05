# RUNBOOK.md — Start / Stop / Debug

## Start (continuous)
.\scripts\start_live_paper.ps1 -Poll 30 -RunMinutes 0

## Stop
.\scripts\stop_live_paper.ps1

## Status
.\scripts\status.ps1

## Debug
- Tail ops logs: Get-Content .\logs\events.jsonl -Tail 50
- Tail journal: Get-Content .\data\paper_journal.jsonl -Tail 50
- State: Get-Content .\data\paper_state.json
- Errors: Get-Content .\logs\live_paper.err.txt -Tail 200
