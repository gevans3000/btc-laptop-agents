import json
import subprocess
import os
from pathlib import Path

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config" / "strategies"
STRATEGY_FILE = CONFIG_DIR / "scalp_1m_sweep.json"
TEMP_STRATEGY_FILE = CONFIG_DIR / "temp_opt.json"
PYTHON_EXE = REPO_ROOT / ".venv" / "Scripts" / "python.exe"


def run_backtest(strategy_name):
    cmd = [
        str(PYTHON_EXE),
        "-m",
        "src.laptop_agents.run",
        "--mode",
        "backtest",
        "--source",
        "mock",
        "--limit",
        "500",
        "--strategy",
        strategy_name,
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    result = subprocess.run(
        cmd, capture_output=True, text=True, env=env, cwd=str(REPO_ROOT)
    )

    stats_path = REPO_ROOT / "runs" / "latest" / "stats.json"
    if stats_path.exists():
        with open(stats_path) as f:
            return json.load(f)
    return None


def main():
    if not STRATEGY_FILE.exists():
        print(f"Error: {STRATEGY_FILE} not found")
        return

    with open(STRATEGY_FILE) as f:
        base_config = json.load(f)

    # Param ranges
    stop_atr_mults = [0.4, 0.8, 1.2, 1.6, 2.0]
    tp_r_mults = [1.5, 2.0, 2.5, 3.0, 4.0]
    entry_band_pcts = [0.0002, 0.0005, 0.0008, 0.0012]

    results = []

    iteration = 0
    for stop in stop_atr_mults:
        for tp in tp_r_mults:
            for band in entry_band_pcts:
                iteration += 1
                if iteration > 50:
                    break

                print(f"Iteration {iteration}: stop={stop}, tp={tp}, band={band}")

                config = json.loads(json.dumps(base_config))
                config["setups"]["pullback_ribbon"]["stop_atr_mult"] = stop
                config["setups"]["pullback_ribbon"]["tp_r_mult"] = tp
                config["setups"]["pullback_ribbon"]["entry_band_pct"] = band

                config["setups"]["sweep_invalidation"]["stop_atr_mult"] = stop * 0.4
                config["setups"]["sweep_invalidation"]["tp_r_mult"] = tp

                with open(TEMP_STRATEGY_FILE, "w") as f:
                    json.dump(config, f, indent=2)

                stats = run_backtest("temp_opt")
                if stats:
                    pnl = stats["net_pnl"]
                    mdd = stats["max_drawdown"]
                    equity = stats.get("starting_balance", 10000)
                    score = pnl - 0.5 * (mdd * equity)

                    results.append(
                        {
                            "params": {"stop": stop, "tp": tp, "band": band},
                            "stats": stats,
                            "score": score,
                        }
                    )

    # Sort by score
    results.sort(key=lambda x: x["score"], reverse=True)

    if results:
        winner = results[0]
        print(f"\nWINNER SCORE: {winner['score']}")
        print(f"PARAMS: {winner['params']}")
        print(f"STATS: {winner['stats']}")

        # Save optimized config
        opt_config = json.loads(json.dumps(base_config))
        opt_config["setups"]["pullback_ribbon"]["stop_atr_mult"] = winner["params"][
            "stop"
        ]
        opt_config["setups"]["pullback_ribbon"]["tp_r_mult"] = winner["params"]["tp"]
        opt_config["setups"]["pullback_ribbon"]["entry_band_pct"] = winner["params"][
            "band"
        ]
        opt_config["setups"]["sweep_invalidation"]["stop_atr_mult"] = (
            winner["params"]["stop"] * 0.4
        )
        opt_config["setups"]["sweep_invalidation"]["tp_r_mult"] = winner["params"]["tp"]

        with open(CONFIG_DIR / "scalp_1m_sweep_optimized.json", "w") as f:
            json.dump(opt_config, f, indent=2)

        # Cleanup
        if TEMP_STRATEGY_FILE.exists():
            TEMP_STRATEGY_FILE.unlink()


if __name__ == "__main__":
    main()
