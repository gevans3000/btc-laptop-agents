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

def tail_lines(path, max_lines=200, max_bytes=250_000):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            start = max(0, size - max_bytes)
            f.seek(start)
            data = f.read()
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        return lines[-max_lines:]
    except Exception:
        return []

def tail_jsonl(path, max_items=200):
    items = []
    for line in reversed(tail_lines(path, max_lines=max_items*2)):
        line = line.strip()
        if not line: 
            continue
        try:
            items.append(json.loads(line))
        except Exception:
            continue
        if len(items) >= max_items:
            break
    items.reverse()
    return items

def summarize(state, control, journal_items):
    last_event = journal_items[-1] if journal_items else None
    last_error = None
    last_candle = None
    counts = {}
    for it in journal_items:
        ev = it.get("event","?")
        counts[ev] = counts.get(ev, 0) + 1
        if ev == "error":
            last_error = it
        if ev == "new_candle":
            last_candle = it
    return {
        "last_event": last_event,
        "last_error": last_error,
        "last_candle": last_candle,
        "counts": counts,
        "state": state,
        "control": control,
    }

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

        if self.path.startswith("/api/summary"):
            state = read_json("data/paper_state.json", {})
            ctrl  = read_json("data/control.json", {"paused": False, "extend_by_sec": 0})
            items = tail_jsonl("data/paper_journal.jsonl", max_items=250)
            s = summarize(state, ctrl, items)

            lp_txt = (read_text("data/live_paper.pid") or "").strip()
            lp_pid = int(lp_txt) if lp_txt.isdigit() else None
            s["now_ms"] = now_ms()
            s["live_paper_pid"] = lp_pid
            s["live_paper_running"] = pid_running(lp_pid)
            self._send_json(200, s)
            return

        if self.path.startswith("/api/journal_tail"):
            q = urllib.parse.urlparse(self.path).query
            qs = urllib.parse.parse_qs(q)
            n = int(qs.get("lines", ["80"])[0])
            items = tail_jsonl("data/paper_journal.jsonl", max_items=max(1, min(500, n)))
            self._send_json(200, {"items": items})
            return

        if self.path.startswith("/api/log_tail"):
            q = urllib.parse.urlparse(self.path).query
            qs = urllib.parse.parse_qs(q)
            which = (qs.get("which", ["live_err"])[0] or "live_err").lower()
            n = int(qs.get("lines", ["120"])[0])
            mp = {
                "live_out": "logs/live_paper.out.txt",
                "live_err": "logs/live_paper.err.txt",
                "dash_out": "logs/dashboard.out.txt",
                "dash_err": "logs/dashboard.err.txt",
            }
            path = mp.get(which, "logs/live_paper.err.txt")
            lines = tail_lines(path, max_lines=max(1, min(1000, n)))
            self._send_json(200, {"which": which, "path": path, "lines": lines})
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
