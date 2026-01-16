import sys
import os
import time
import json
import subprocess
import signal
import platform
from pathlib import Path

# Config
MAX_RESTARTS = 3
HEARTBEAT_TIMEOUT = 30  # Seconds
CHECK_INTERVAL = 2      # Seconds
STARTUP_GRACE_PERIOD = 15 # Seconds to allow for initial startup
HEARTBEAT_FILE = Path("logs/heartbeat.json")

def get_heartbeat_age():
    if not HEARTBEAT_FILE.exists():
        # If file is missing, treat as infinitely old
        return 9999
    try:
        with open(HEARTBEAT_FILE, "r") as f:
            data = json.load(f)
            ts = data.get("unix_ts", 0)
            return time.time() - ts
    except Exception:
        return 9999

def kill_process(proc):
    print(f"[SUPERVISOR] Killing PID {proc.pid}...")
    if platform.system() == "Windows":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], 
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

def main():
    agent_args = sys.argv[1:]
    
    env = os.environ.copy()
    repo_root = Path(__file__).parent.parent
    src_path = repo_root / "src"
    env["PYTHONPATH"] = str(src_path) + os.pathsep + env.get("PYTHONPATH", "")
    
    cmd = [sys.executable, "-m", "laptop_agents.run"] + agent_args
    
    restarts = 0
    
    while restarts < MAX_RESTARTS:
        print(f"\n[SUPERVISOR] Starting Agent (Attempt {restarts + 1}/{MAX_RESTARTS})...")
        print(f"[SUPERVISOR] CMD: {' '.join(cmd)}")
        
        # Cleanup old heartbeat
        if HEARTBEAT_FILE.exists():
            try:
                HEARTBEAT_FILE.unlink()
            except Exception:
                pass

        creationflags = 0
        preexec_fn = None
        
        if platform.system() == "Windows":
             creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
             preexec_fn = os.setsid

        proc = subprocess.Popen(
            cmd,
            env=env,
            creationflags=creationflags,
            preexec_fn=preexec_fn
        )
        
        print(f"[SUPERVISOR] Agent running with PID {proc.pid}")
        start_time = time.time()
        
        try:
            while True:
                ret = proc.poll()
                if ret is not None:
                    if ret == 0:
                        print("[SUPERVISOR] Agent exited successfully (0).")
                        return 0
                    else:
                        print(f"[SUPERVISOR] Agent crashed with exit code {ret}.")
                        break 
                
                # Grace period check
                if time.time() - start_time < STARTUP_GRACE_PERIOD:
                    time.sleep(CHECK_INTERVAL)
                    continue

                age = get_heartbeat_age()
                if age > HEARTBEAT_TIMEOUT:
                    print(f"[SUPERVISOR] WARNING: Heartbeat stale ({age:.1f}s > {HEARTBEAT_TIMEOUT}s).")
                    kill_process(proc)
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutError:
                        print("[SUPERVISOR] Force kill required.")
                    break 
                    
                time.sleep(CHECK_INTERVAL)
                
        except KeyboardInterrupt:
            print("\n[SUPERVISOR] KeyboardInterrupt received. Stopping agent...")
            kill_process(proc)
            return 0
        
        restarts += 1
        if restarts < MAX_RESTARTS:
            print(f"[SUPERVISOR] Restarting in 5 seconds...")
            time.sleep(5)
        else:
            print("[SUPERVISOR] FATAL: Max restarts exceeded.")
            return 1
            
    return 1

if __name__ == "__main__":
    sys.exit(main())
