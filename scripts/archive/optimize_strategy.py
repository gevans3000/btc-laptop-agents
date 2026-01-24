from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def main():
    # Path resolution
    here = Path(__file__).resolve()
    repo_root = here.parent.parent
    sys.path.append(str(repo_root / "src"))

    from laptop_agents.backtest.engine import run_backtest_position_mode, set_context
    from laptop_agents.core.logger import logger
    from laptop_agents.data.loader import load_bitunix_candles, load_mock_candles
    from laptop_agents.trading.helpers import normalize_candle_order

    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["mock", "bitunix"], default="bitunix")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--limit", type=int, default=500)
    args = ap.parse_args()

    # Setup context (required by backtest engine for artifact writing,
    # though we'll mainly care about the returned dict here)
    latest_dir = repo_root / "runs" / "latest"
    latest_dir.mkdir(parents=True, exist_ok=True)

    def dummy_append_event(obj, paper=False):
        pass  # Silence events during optimization iterations

    set_context(latest_dir, dummy_append_event)

    # Load candles
    logger.info(f"Loading {args.limit} candles from {args.source} for {args.symbol}...")
    if args.source == "bitunix":
        candles = load_bitunix_candles(args.symbol, "1m", args.limit)
    else:
        candles = load_mock_candles(args.limit)

    candles = normalize_candle_order(candles)
    logger.info(f"Loaded {len(candles)} candles.")

    # SMA settings to test
    fast_sma_list = [5, 8, 10, 12]
    slow_sma_list = [15, 21, 30, 50]

    # Defaults for other params
    starting_balance = 10_000.0
    fees_bps = 2.0
    slip_bps = 0.5
    risk_pct = 1.0
    stop_bps = 30.0
    tp_r = 1.5

    results = []

    logger.info(
        f"Starting parameter grid search ({len(fast_sma_list) * len(slow_sma_list)} combos)..."
    )
    for fast in fast_sma_list:
        for slow in slow_sma_list:
            if fast >= slow:
                continue

            try:
                res = run_backtest_position_mode(
                    candles=candles,
                    starting_balance=starting_balance,
                    fees_bps=fees_bps,
                    slip_bps=slip_bps,
                    risk_pct=risk_pct,
                    stop_bps=stop_bps,
                    tp_r=tp_r,
                    fast_sma=fast,
                    slow_sma=slow,
                )

                stats = res["stats"]
                results.append(
                    {
                        "fast_sma": fast,
                        "slow_sma": slow,
                        "net_pnl": stats["net_pnl"],
                        "trades": stats["trades"],
                        "win_rate": stats["win_rate"],
                        "max_drawdown": stats["max_drawdown"],
                    }
                )
            except Exception as e:
                logger.error(f"Failed combo fast={fast}, slow={slow}: {e}")

    # Sort by Net PnL descending
    results.sort(key=lambda x: x["net_pnl"], reverse=True)

    # Save to CSV
    output_path = latest_dir / "optimization_results.csv"
    if results:
        with output_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
        logger.info(f"Optimization results saved to {output_path}")

        # Print Top 3
        print("\n" + "=" * 40)
        print("      STRATEGY OPTIMIZER RESULTS      ")
        print("=" * 40)
        print(f"{'Rank':<5} {'SMA':<12} {'PnL':<10} {'Trades':<8}")
        print("-" * 40)
        for i, r in enumerate(results[:3]):
            sma_str = f"{r['fast_sma']}/{r['slow_sma']}"
            pnl_str = f"${r['net_pnl']:,.2f}"
            print(f"{i + 1:<5} {sma_str:<12} {pnl_str:<10} {r['trades']:<8}")
        print("=" * 40 + "\n")
    else:
        logger.warning("No results found.")


if __name__ == "__main__":
    main()
