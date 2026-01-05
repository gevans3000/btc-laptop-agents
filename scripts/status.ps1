Set-Location "$env:USERPROFILE\trading\btc-laptop-agents"

"=== DASHBOARD ==="
if (Test-Path .\data\dashboard.pid) {
  $dp = Get-Content .\data\dashboard.pid
  "dashboard.pid=$dp"
} else { "dashboard.pid=missing" }

"=== LIVE PAPER ==="
if (Test-Path .\data\live_paper.pid) {
  $lp = Get-Content .\data\live_paper.pid
  "live_paper.pid=$lp"
} else { "live_paper.pid=missing" }

"=== STATE (paper_state.json) ==="
if (Test-Path .\data\paper_state.json) { Get-Content .\data\paper_state.json } else { "no state yet" }

"=== JOURNAL (tail 10) ==="
if (Test-Path .\data\paper_journal.jsonl) { Get-Content .\data\paper_journal.jsonl -Tail 10 } else { "no journal yet" }

"=== ERR LOG (tail 30) ==="
if (Test-Path .\logs\live_paper.err.txt) { Get-Content .\logs\live_paper.err.txt -Tail 30 } else { "no err log" }
