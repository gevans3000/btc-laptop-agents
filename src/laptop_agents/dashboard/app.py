
from flask import Flask, render_template_string
import json
from pathlib import Path
import logging

# Disable flask logging for cleaner terminal
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)
HEARTBEAT_PATH = Path("logs/heartbeat.json")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Laptop Agents Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0b0e14;
            --card-bg: #151921;
            --primary: #38bdf8;
            --accent: #818cf8;
            --success: #10b981;
            --text: #f1f5f9;
            --text-dim: #94a3b8;
            --border: #262c36;
        }
        body {
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg);
            color: var(--text);
            margin: 0;
            display: flex;
            flex-direction: column;
            align-items: center;
            min-height: 100vh;
            padding: 2rem;
        }
        .container {
            width: 100%;
            max-width: 1000px;
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
            width: 100%;
        }
        h1 {
            font-weight: 300;
            margin: 0;
            background: linear-gradient(135deg, var(--primary), var(--accent));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 2rem;
        }
        .status-badge {
            display: flex;
            align-items: center;
            background: rgba(16, 185, 129, 0.1);
            color: var(--success);
            padding: 0.5rem 1rem;
            border-radius: 20px;
            font-size: 0.875rem;
            border: 1px solid rgba(16, 185, 129, 0.2);
        }
        .pulse {
            width: 8px;
            height: 8px;
            background-color: var(--success);
            border-radius: 50%;
            margin-right: 8px;
            box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7);
            animation: pulse-green 2s infinite;
        }
        @keyframes pulse-green {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 10px rgba(16, 185, 129, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }
        .card {
            background: var(--card-bg);
            border-radius: 16px;
            padding: 1.5rem;
            border: 1px solid var(--border);
            transition: transform 0.2s, border-color 0.2s;
        }
        .card:hover {
            transform: translateY(-4px);
            border-color: var(--primary);
        }
        .label {
            font-size: 0.75rem;
            color: var(--text-dim);
            text-transform: uppercase;
            letter-spacing: 0.1em;
            margin-bottom: 0.5rem;
        }
        .value {
            font-size: 1.75rem;
            font-weight: 600;
        }
        .footer {
            text-align: center;
            color: var(--text-dim);
            font-size: 0.875rem;
            margin-top: auto;
        }
    </style>
    <meta http-equiv="refresh" content="2">
</head>
<body>
    <div class="container">
        <header>
            <h1>Antigravity Dashboard</h1>
            <div class="status-badge">
                <div class="pulse"></div>
                SYSTEM LIVE
            </div>
        </header>

        <div class="grid">
            <div class="card">
                <div class="label">Symbol</div>
                <div class="value">{{ data.symbol }}</div>
            </div>
            <div class="card">
                <div class="label">Total Equity</div>
                <div class="value">${{ "{:,.2f}".format(data.equity) }}</div>
            </div>
            <div class="card">
                <div class="label">Session Duration</div>
                <div class="value">{{ "{:.0f}s".format(data.elapsed) }}</div>
            </div>
            <div class="card">
                <div class="label">Last Heartbeat</div>
                <div class="value" style="font-size: 1rem; color: var(--text-dim);">{{ data.ts }}</div>
            </div>
        </div>

        <div class="footer">
            Auto-refreshing every 2 seconds.
        </div>
    </div>
</body>
</html>
"""

@app.route("/")
def index():
    data = {"symbol": "Searching...", "equity": 0.0, "elapsed": 0, "ts": "-"}
    if HEARTBEAT_PATH.exists():
        try:
            with open(HEARTBEAT_PATH) as f:
                data = json.load(f)
        except Exception:
            pass
    return render_template_string(HTML_TEMPLATE, data=data)

def run_dashboard(port=5000):
    app.run(host="127.0.0.1", port=port, debug=False)

if __name__ == "__main__":
    run_dashboard()
