from __future__ import annotations
import os
import json
import time
from flask import Flask, render_template, jsonify
from pathlib import Path

app = Flask(__name__)

# Paths
# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
WORKSPACE_DIR = REPO_ROOT / ".workspace"
HEARTBEAT_PATH = WORKSPACE_DIR / "logs" / "heartbeat.json"
BROKER_STATE_PATH = WORKSPACE_DIR / "paper" / "broker_state.json"
EVENTS_PATH = WORKSPACE_DIR / "paper" / "events.jsonl"
LOG_PATH = WORKSPACE_DIR / "logs" / "system.jsonl"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def status():
    # Read Heartbeat
    heartbeat = {}
    if HEARTBEAT_PATH.exists():
        try:
            with open(HEARTBEAT_PATH) as f:
                heartbeat = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            app.logger.warning(f"Error reading heartbeat: {e}")

    # Read Broker State
    broker = {}
    if BROKER_STATE_PATH.exists():
        try:
            with open(BROKER_STATE_PATH) as f:
                broker = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            app.logger.warning(f"Error reading broker state: {e}")

    # Read Recent Events (last 10)
    events = []
    if EVENTS_PATH.exists():
        try:
            with open(EVENTS_PATH) as f:
                lines = f.readlines()
                events = [json.loads(line) for line in lines[-10:]]
        except (json.JSONDecodeError, OSError) as e:
            app.logger.warning(f"Error reading events: {e}")

    # Read Recent Logs
    logs = []
    if LOG_PATH.exists():
        try:
            with open(LOG_PATH, encoding="utf-8") as f:
                lines = f.readlines()
                logs = lines[-30:]
        except OSError as e:
            app.logger.warning(f"Error reading logs: {e}")

    return jsonify(
        {
            "server_time": time.time(),
            "heartbeat": heartbeat,
            "broker": broker,
            "events": events,
            "logs": logs,
        }
    )


def run_dashboard(port=5000):
    """Run the dashboard server."""
    # Ensure templates folder exists
    template_dir = Path(__file__).parent / "templates"
    template_dir.mkdir(exist_ok=True)

    port = int(os.environ.get("DASHBOARD_PORT", port))
    print(f"Starting Trading Dashboard on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    run_dashboard()
