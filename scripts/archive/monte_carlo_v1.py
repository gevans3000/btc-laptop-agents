
import csv
import json
import random
import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
LATEST_TRADES = REPO_ROOT / "runs" / "latest" / "trades.csv"
PYTHON_EXE = REPO_ROOT / ".venv" / "Scripts" / "python.exe"

def run_backtest(strategy_name, source="bitunix", limit=1000):
    print(f"Running backtest for {strategy_name} on {source} data ({limit} bars)...")
    cmd = [
        str(PYTHON_EXE), "-m", "src.laptop_agents.run",
        "--mode", "backtest",
        "--source", source,
        "--limit", str(limit),
        "--strategy", strategy_name
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(REPO_ROOT))
    
    if not LATEST_TRADES.exists():
        print("Error: Backtest did not produce trades.csv")
        return False
    return True

def monte_carlo_simulation(trades_pnl, starting_balance=10000.0, iterations=1000, bootstrap=True):
    if not trades_pnl:
        return None

    results = []
    
    for _ in range(iterations):
        if bootstrap:
            # Sample with replacement
            sim_trades = [random.choice(trades_pnl) for _ in range(len(trades_pnl))]
        else:
            # Shuffle existing trades (path analysis only)
            sim_trades = list(trades_pnl)
            random.shuffle(sim_trades)
        
        equity = starting_balance
        max_equity = starting_balance
        max_drawdown = 0.0
        
        for pnl in sim_trades:
            equity += pnl
            max_equity = max(max_equity, equity)
            drawdown = (max_equity - equity) / max_equity if max_equity > 0 else 0
            max_drawdown = max(max_drawdown, drawdown)
            
        results.append({
            "final_equity": equity,
            "max_drawdown": max_drawdown,
            "net_pnl": equity - starting_balance
        })
        
    return results

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Monte Carlo Simulation for Trading Strategies")
    parser.add_argument("--strategy", type=str, help="Strategy name to backtest first")
    parser.add_argument("--source", type=str, default="bitunix", help="Data source for backtest (mock/bitunix)")
    parser.add_argument("--limit", type=int, default=1000, help="Number of bars for backtest")
    parser.add_argument("--iterations", type=int, default=1000, help="Number of MC iterations")
    parser.add_argument("--starting-balance", type=float, default=10000.0)
    parser.add_argument("--no-bootstrap", action="store_true", help="Use shuffle instead of sampling with replacement")
    
    args = parser.parse_args()
    bootstrap = not args.no_bootstrap
    
    if args.strategy:
        if not run_backtest(args.strategy, args.source, args.limit):
            return

    if not LATEST_TRADES.exists():
        print(f"Error: {LATEST_TRADES} not found. Run a backtest first.")
        return

    pnls = []
    with open(LATEST_TRADES, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pnls.append(float(row["pnl"]))

    if not pnls:
        print("No trades found in trades.csv. Simulation aborted.")
        return

    mode_str = "Bootstrapping" if bootstrap else "Shuffling"
    print(f"Loaded {len(pnls)} trades. Starting {args.iterations} Iterations ({mode_str})...")
    
    results = monte_carlo_simulation(pnls, args.starting_balance, args.iterations, bootstrap=bootstrap)
    
    if not results:
        return

    # Analyze results
    final_equities = sorted([r["final_equity"] for r in results])
    drawdowns = sorted([r["max_drawdown"] for r in results])
    
    p5 = final_equities[int(len(final_equities) * 0.05)]
    p50 = final_equities[int(len(final_equities) * 0.50)]
    p95 = final_equities[int(len(final_equities) * 0.95)]
    
    max_dd_mean = sum(drawdowns) / len(drawdowns)
    max_dd_95p = drawdowns[int(len(drawdowns) * 0.95)]
    
    ruin_count = sum(1 for r in results if r["max_drawdown"] > 0.20)
    prob_ruin = ruin_count / len(results)

    print("\n" + "="*40)
    print("      MONTE CARLO SIMULATION RESULTS")
    print("="*40)
    print(f"Trades Sampled:    {len(pnls)}")
    print(f"Iterations:        {args.iterations}")
    print(f"Starting Balance:  ${args.starting_balance:,.2f}")
    print("-" * 40)
    print(f"5% Percentile:     ${p5:,.2f} (Worst Case)")
    print(f"50% Percentile:    ${p50:,.2f} (Median)")
    print(f"95% Percentile:    ${p95:,.2f} (Best Case)")
    print("-" * 40)
    print(f"Avg Max Drawdown:  {max_dd_mean*100:.2f}%")
    print(f"95% Max Drawdown:  {max_dd_95p*100:.2f}%")
    print(f"Prob. of >20% DD:  {prob_ruin*100:.2f}%")
    print("="*40)

if __name__ == "__main__":
    main()
