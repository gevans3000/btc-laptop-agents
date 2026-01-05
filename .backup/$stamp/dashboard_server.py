import json, os, time, subprocess, urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

def now_ms(): return int(time.time()*1000)

def read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as f: return f.read()
    except Exception:
        return ""

def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except Exception:
        return default

def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)

def pid_running(pid):
    if not pid: return False
    # Windows: os.kill(pid, 0) is not reliable; use tasklist.
    if os.name == "nt":
        try:
            r = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True
            )
            out = (r.stdout or "").strip()
            if (not out) or out.upper().startswith('"INFO:'):
                return False
            return str(pid) in out
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False

def kill_pid_windows(pid):
    try:
        r = subprocess.run(["taskkill","/PID",str(pid),"/T","/F"], capture_output=True, text=True)
        return r.returncode == 0
    except Exception:
        return False

class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def _send_json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/status"):
            state = read_json("data/paper_state.json", {})
            ctrl  = read_json("data/control.json", {"paused": False, "extend_by_sec": 0})

            lp_txt = (read_text("data/live_paper.pid") or "").strip()
            dp_txt = (read_text("data/dashboard.pid") or "").strip()

            lp_pid = int(lp_txt) if lp_txt.isdigit() else None
            dp_pid = int(dp_txt) if dp_txt.isdigit() else None

            self._send_json(200, {
                "now_ms": now_ms(),
                "dashboard_pid": dp_pid,
                "live_paper_pid": lp_pid,
                "live_paper_running": pid_running(lp_pid),
                "state": state,
                "control": ctrl
            })
            return
        return super().do_GET()

    def do_POST(self):
        if not self.path.startswith("/api/"):
            return self._send_json(404, {"ok": False, "error": "not found"})

        ctrl_path = "data/control.json"
        ctrl = read_json(ctrl_path, {"paused": False, "extend_by_sec": 0})

        if self.path.startswith("/api/pause"):
            ctrl["paused"] = True; ctrl["ts"] = now_ms()
            write_json(ctrl_path, ctrl)
            return self._send_json(200, {"ok": True, "paused": True})

        if self.path.startswith("/api/resume"):
            ctrl["paused"] = False; ctrl["ts"] = now_ms()
            write_json(ctrl_path, ctrl)
            return self._send_json(200, {"ok": True, "paused": False})

        if self.path.startswith("/api/extend"):
            q = urllib.parse.urlparse(self.path).query
            qs = urllib.parse.parse_qs(q)
            sec = int(qs.get("seconds", ["3600"])[0])
            ctrl["extend_by_sec"] = int(ctrl.get("extend_by_sec", 0) or 0) + sec
            ctrl["ts"] = now_ms()
            write_json(ctrl_path, ctrl)
            return self._send_json(200, {"ok": True, "extend_by_sec": ctrl["extend_by_sec"]})

        if self.path.startswith("/api/stop"):
            lp_txt = (read_text("data/live_paper.pid") or "").strip()
            killed = False
            if lp_txt.isdigit():
                killed = kill_pid_windows(int(lp_txt))
            try: os.remove("data/live_paper.pid")
            except Exception: pass
            return self._send_json(200, {"ok": True, "killed": killed})

        return self._send_json(404, {"ok": False, "error": "not found"})

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--bind", default="127.0.0.1")
    args = ap.parse_args()
    httpd = ThreadingHTTPServer((args.bind, args.port), Handler)
    print(f"Dashboard server listening on http://{args.bind}:{args.port}/", flush=True)
    httpd.serve_forever()

if __name__ == "__main__":
    main()
