import os
import json
import csv
import uuid
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

def detect_repo_root():
    """Detect the repository root by looking for a marker file."""
    current_path = Path.cwd()
    while current_path != current_path.parent:
        if (current_path / "pyproject.toml").exists():
            return current_path
        current_path = current_path.parent
    return Path.cwd()

def ensure_directory(directory):
    """Ensure the directory exists, creating it if necessary."""
    Path(directory).mkdir(parents=True, exist_ok=True)

def generate_mock_candles():
    """Generate mock BTC price candles for testing."""
    return [
        {"timestamp": "2023-01-01T00:00:00Z", "open": 16000.0, "high": 16100.0, "low": 15900.0, "close": 16050.0, "volume": 100.0},
        {"timestamp": "2023-01-01T00:05:00Z", "open": 16050.0, "high": 16150.0, "low": 16000.0, "close": 16100.0, "volume": 120.0},
        {"timestamp": "2023-01-01T00:10:00Z", "open": 16100.0, "high": 16200.0, "low": 16050.0, "close": 16150.0, "volume": 150.0},
    ]

def fetch_bitunix_candles(symbol, interval, limit):
    """Fetch candles from Bitunix public API."""
    url = f"https://api.bitunix.com/v1/futures/public/kline?symbol={symbol}&interval={interval}&limit={limit}"
    headers = {"User-Agent": "laptop_agents/1.0"}
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
            if data.get("code") != 0:
                raise RuntimeError(f"Bitunix API error: {data}")
            candles = []
            for item in data.get("data", []):
                candle = {
                    "timestamp": item[0],
                    "open": float(item[1]),
                    "high": float(item[2]),
                    "low": float(item[3]),
                    "close": float(item[4]),
                    "volume": float(item[5]),
                }
                candles.append(candle)
            return candles
    except urllib.error.URLError as e:
        raise RuntimeError(f"Failed to fetch Bitunix candles: {e}")

def calculate_sma(candles, window=2):
    """Calculate Simple Moving Average (SMA) for the given candles."""
    closes = [candle["close"] for candle in candles]
    return sum(closes[-window:]) / window

def simulate_trade(candles, balance=10000.0):
    """Simulate a simple trade based on SMA strategy."""
    sma = calculate_sma(candles)
    current_price = candles[-1]["close"]
    signal = "BUY" if current_price > sma else "SELL"

    trade = {
        "trade_id": str(uuid.uuid4()),
        "signal": signal,
        "price": current_price,
        "quantity": balance / current_price,
        "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
    }
    return trade

def write_events(events, output_dir):
    """Write events to events.jsonl file."""
    events_path = Path(output_dir) / "events.jsonl"
    with open(events_path, "w") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")

def write_trades(trades, output_dir):
    """Write trades to trades.csv file."""
    trades_path = Path(output_dir) / "trades.csv"
    with open(trades_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["trade_id", "signal", "price", "quantity", "timestamp"])
        writer.writeheader()
        writer.writerows(trades)

def write_state(state, output_dir):
    """Write state to state.json file."""
    state_path = Path(output_dir) / "state.json"
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)

def generate_html_summary(run_id, starting_balance, ending_balance, trades, events_tail, output_dir):
    """Generate a static HTML summary of the run."""
    trade_rows = ""
    for trade in trades:
        trade_rows += f"""
        <tr>
            <td>{trade["trade_id"]}</td>
            <td>{trade["signal"]}</td>
            <td>${trade["price"]:.2f}</td>
            <td>{trade["quantity"]:.8f}</td>
            <td>{trade["timestamp"]}</td>
        </tr>
        """
    
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Run Summary</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        .events {{ font-family: monospace; white-space: pre; background-color: #f5f5f5; padding: 10px; }}
    </style>
</head>
<body>
    <h1>Run Summary</h1>
    <p><strong>Run ID:</strong> {run_id}</p>
    <p><strong>Starting Balance:</strong> ${starting_balance:.2f}</p>
    <p><strong>Ending Balance:</strong> ${ending_balance:.2f}</p>
    <p><strong>Net PnL:</strong> ${ending_balance - starting_balance:.2f}</p>

    <h2>Trades</h2>
    <table>
        <tr>
            <th>Trade ID</th>
            <th>Signal</th>
            <th>Price</th>
            <th>Quantity</th>
            <th>Timestamp</th>
        </tr>
        {trade_rows}
    </table>

    <h2>Events Tail</h2>
    <div class="events">{events_tail}</div>
</body>
</html>
    """
    summary_path = Path(output_dir) / "summary.html"
    with open(summary_path, "w") as f:
        f.write(html_content)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run trading simulation.")
    parser.add_argument("--source", choices=["mock", "bitunix"], default="mock", help="Data source (default: mock)")
    parser.add_argument("--symbol", default="BTCUSDT", help="Symbol (default: BTCUSDT)")
    parser.add_argument("--interval", default="1m", help="Interval (default: 1m)")
    parser.add_argument("--limit", type=int, default=200, help="Limit (default: 200)")
    args = parser.parse_args()

    repo_root = detect_repo_root()
    output_dir = repo_root / "runs" / "latest"
    ensure_directory(output_dir)

    run_id = str(uuid.uuid4())
    starting_balance = 10000.0
    
    try:
        if args.source == "bitunix":
            candles = fetch_bitunix_candles(args.symbol, args.interval, args.limit)
            events = [
                {"event": "RunStarted", "run_id": run_id, "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00','Z')},
                {"event": "MarketDataLoaded", "source": "bitunix", "symbol": args.symbol, "interval": args.interval, "count": len(candles), "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00','Z')},
            ]
        else:
            candles = generate_mock_candles()
            events = [
                {"event": "RunStarted", "run_id": run_id, "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00','Z')},
                {"event": "MarketDataLoaded", "source": "mock", "symbol": "BTCUSDT", "interval": "1m", "count": len(candles), "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00','Z')},
            ]
    except RuntimeError as e:
        error_event = {"event": "Error", "message": str(e), "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00','Z')}
        write_events([error_event], output_dir)
        sys.exit(1)

    trade = simulate_trade(candles, starting_balance)
    ending_balance = starting_balance + (trade["price"] * trade["quantity"] - starting_balance)

    events.extend([
        {"event": "SignalGenerated", "signal": trade["signal"], "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00','Z')},
        {"event": "TradeSimulated", "trade": trade, "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00','Z')},
        {"event": "RunFinished", "run_id": run_id, "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00','Z')},
    ])

    write_events(events, output_dir)
    write_trades([trade], output_dir)
    write_state({"run_id": run_id, "balance": ending_balance}, output_dir)

    events_tail = "\n".join(json.dumps(event) for event in events[-3:])
    generate_html_summary(run_id, starting_balance, ending_balance, [trade], events_tail, output_dir)

if __name__ == "__main__":
    main()

