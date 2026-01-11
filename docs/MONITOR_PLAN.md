# Quick Plan: PowerShell Monitor HUD

## Goal
Create a lightweight script `scripts/monitor.ps1` that acts as a real-time dashboard for the trading bot running in the background.

## Features
1.  **Health Check**: Calculates "seconds since last heartbeat" to detect freezes.
2.  **Visual Status**: Uses Red/Green/Yellow text to show system state at a glance.
3.  **Key Metrics**: Displays Equity, Candle Progress, and Symbol.
4.  **Kill Switch State**: Shows if the Kill Switch is Active or Inactive.
5.  **Log Tailing**: Shows the last few lines of `logs/watchdog.log` to see process restarts.

---

## Instructions for Gemini 3 Flash (Copy & Paste)

**Prompt:**

> Write a PowerShell script named `scripts/monitor.ps1` for my trading bot.
>
> **Requirements:**
> 1.  **Loop & Clear**: Run in a `while($true)` loop that clears the screen (`Clear-Host`) every 3 seconds.
> 2.  **Heartbeat Check**: Read `logs/heartbeat.json` (JSON format: `{"ts": "...", "equity": 10000.0, "candle_idx": 50}`).
>     *   Parse the `ts` timestamp and compare it to `Get-Date` (UTC).
>     *   If `Last Update` < 90 seconds ago, write "STATUS: ONLINE" in Green.
>     *   If `Last Update` > 90 seconds, write "STATUS: STALE/FROZEN" in Red.
> 3.  **Kill Switch**: Check if `config/KILL_SWITCH.txt` contains "TRUE". Display "KILL SWITCH: ACTIVE" in Red if true, else "READY" in Green.
> 4.  **Display Metrics**: Print Symbol, Equity (formatted as currency), and Candle Index.
> 5.  **Log Tail**: Read and display the last 5 lines of `logs/watchdog.log` in Gray to show process activity.
> 6.  **Error Handling**: If `heartbeat.json` is missing or locked, just print "Waiting for heartbeat..." nicely without crashing.
