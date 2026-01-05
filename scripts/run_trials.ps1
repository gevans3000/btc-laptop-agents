<#
Run paper trading trials and generate reports

Usage:
  .\scripts\run_trials.ps1 -Runs <num> -Loops <num> -Poll <seconds> -Symbol <symbol> -Interval <interval>
  
  -Runs: Number of trial runs (default 1)
  -Loops: Loops per run (default 50)
  -Poll: Poll interval in seconds (default 5)
  -Symbol: Trading symbol (default BTCUSDT)
  -Interval: Time interval (default 5m)
#>

param(
    [int]$Runs = 1,
    [int]$Loops = 50,
    [int]$Poll = 5,
    [string]$Symbol = "BTCUSDT",
    [string]$Interval = "5m"
)

$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $repo

# Ensure reports directory exists
$reportsDir = Join-Path $repo "reports"
if (!(Test-Path $reportsDir)) {
    New-Item -ItemType Directory -Path $reportsDir -Force | Out-Null
}

# Generate trial ID
trial_id = "trial_" + (Get-Date -Format "yyyyMMdd_HHmmss")

Write-Host "[TRIALS] Starting $Runs runs with $Loops loops each"
Write-Host "[TRIALS] Symbol: $Symbol, Interval: $Interval, Poll: $Poll"

# Run trials
for ($runNum = 1; $runNum -le $Runs; $runNum++) {
    Write-Host "[TRIALS] Starting run $runNum of $Runs..."
    
    # Run the live paper loop
    $startTime = Get-Date
    $outputFile = Join-Path $reportsDir "trial_$trial_id\run_$runNum\output.txt"
    $errorFile = Join-Path $reportsDir "trial_$trial_id\run_$runNum\error.txt"
    
    # Ensure run directory exists
    $runDir = Split-Path -Parent $outputFile
    if (!(Test-Path $runDir)) {
        New-Item -ItemType Directory -Path $runDir -Force | Out-Null
    }
    
    try {
        $args = @(
            "scripts\live_paper_loop.py",
            "--symbol", $Symbol,
            "--interval", $Interval,
            "--limit", "90",
            "--journal", "data\paper_journal_$trial_id.jsonl",
            "--state", "data\paper_state_$trial_id.json",
            "--control", "data\control_$trial_id.json",
            "--poll", $Poll,
            "--max-loops", $Loops
        )
        
        $p = Start-Process -FilePath "python" -ArgumentList $args -WorkingDirectory $repo -NoNewWindow -RedirectStandardOutput $outputFile -RedirectStandardError $errorFile -PassThru
        
        # Wait for completion
        Wait-Process -Id $p.Id
        
        $endTime = Get-Date
        $duration = ($endTime - $startTime).TotalSeconds
        
        Write-Host "[TRIALS] Run $runNum completed in $([math]::Round($duration, 1)) seconds"
        
        # Generate report
        $reportDir = Join-Path $reportsDir "trial_$trial_id\run_$runNum"
        $reportHtml = Join-Path $reportDir "report.html"
        
        # Simple HTML report
        $htmlContent = @"
<!DOCTYPE html>
<html>
<head>
    <title>Trial Report: $trial_id - Run $runNum</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        h1 { color: #333; }
        .summary { background: #f5f5f5; padding: 15px; border-radius: 5px; }
        .stats { margin: 20px 0; }
    </style>
</head>
<body>
    <h1>Trial Report: $trial_id - Run $runNum</h1>
    <div class="summary">
        <h2>Summary</h2>
        <p><strong>Symbol:</strong> $Symbol</p>
        <p><strong>Interval:</strong> $Interval</p>
        <p><strong>Loops:</strong> $Loops</p>
        <p><strong>Poll Interval:</strong> $Poll seconds</p>
        <p><strong>Duration:</strong> $([math]::Round($duration, 1)) seconds</p>
        <p><strong>Started:</strong> $($startTime.ToString("yyyy-MM-dd HH:mm:ss"))</p>
        <p><strong>Completed:</strong> $($endTime.ToString("yyyy-MM-dd HH:mm:ss"))</p>
    </div>
    <div class="stats">
        <h2>Statistics</h2>
        <p>Statistics would be loaded from the journal file here...</p>
    </div>
</body>
</html>
""@
        
        Set-Content -Path $reportHtml -Value $htmlContent -Encoding UTF8
        
        # Create latest.html (overwrite)
        $latestHtml = Join-Path $reportsDir "latest.html"
        Copy-Item -Path $reportHtml -Destination $latestHtml -Force -ErrorAction SilentlyContinue
        
        # Create latest_run.json
        $latestRunJson = Join-Path $reportsDir "latest_run.json"
        $runInfo = @{
            trial_id = $trial_id
            created_ts = Get-Date -Format "o"
            report_path = $reportHtml
            symbol = $Symbol
            interval = $Interval
            loops = $Loops
            poll = $Poll
            runs = $Runs
            run_number = $runNum
            duration_seconds = [math]::Round($duration, 1)
        } | ConvertTo-Json -Depth 5
        
        Set-Content -Path $latestRunJson -Value $runInfo -Encoding UTF8 -Force
        
        Write-Host "[TRIALS] Generated report: $reportHtml"
        Write-Host "[TRIALS] Updated latest.html and latest_run.json"
        
    } catch {
        $errorMsg = $_.Exception.Message
        Write-Host "[TRIALS] Error in run $runNum: $errorMsg" -ForegroundColor Red
    }
}

Write-Host "[TRIALS] All runs completed. Latest results:"
Write-Host "  - HTML: $reportsDir\latest.html"
Write-Host "  - JSON: $reportsDir\latest_run.json"
