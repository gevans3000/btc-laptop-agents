Remove-Item -Path "src/laptop_agents/data/providers/binance_futures.py" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "src/laptop_agents/data/providers/bybit_derivatives.py" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "src/laptop_agents/data/providers/kraken_spot.py" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "src/laptop_agents/data/providers/okx_swap.py" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "src/laptop_agents/agents/planner.py" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "src/laptop_agents/agents/researcher.py" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "tests/regressions/" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "src/laptop_agents/data/memory_main.jsonl" -Force -ErrorAction SilentlyContinue
Write-Host "Cleanup complete."
