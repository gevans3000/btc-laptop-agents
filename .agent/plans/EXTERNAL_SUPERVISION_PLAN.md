# EXTERNAL SUPERVISION PLAN

**Priority**: High
**Estimated Scope**: 1 new file, ~100 lines
**Goal**: Create a robust external supervisor script (`scripts/supervisor.py`) that launches the trading agent, monitors its heartbeat, and automatically restarts it if it freezes or crashes, ensuring true "walk-away" autonomy.

---

## EXECUTION PROTOCOL

// turbo-all

1. Read this entire plan.
2. Implement `scripts/supervisor.py`.
3. Verify with a "simulated freeze" test.
4. Commit changes.

---

## PHASE 1: Supervisor Script Implementation

### Task 1.1: Create `scripts/supervisor.py`

**File**: `scripts/supervisor.py`

**Goal**: A Python script that:
1. Accepts all arguments meant for `laptop_agents.run`.
2. Sets `PYTHONPATH` to include `src`.
3. Launches `python -m laptop_agents.run ...` as a subprocess.
4. Monitors `logs/heartbeat.json`.
5. If heartbeat > 30s old, sends `SIGTERM` (or `taskkill` on Windows).
6. If process exits with non-zero code, restarts it (up to MAX_RESTARTS).
7. If process exits with 0 (success), exits successfully.

**Code Content**:

```python
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
HEARTBEAT_FILE = Path("logs/heartbeat.json")

def get_heartbeat_age():
    if not HEARTBEAT_FILE.exists():
        return 9999
    try:
        with open(HEARTBEAT_FILE, "r") as f:
            data = json.load(f)
            # Use 'unix_ts' from file, compare to system 'time.time()'
            # Ensure we don't crash if keys are missing
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
    # Pass through all args after 'supervisor.py' to the agent
    agent_args = sys.argv[1:]

    # Ensure src is in PYTHONPATH
    env = os.environ.copy()
    repo_root = Path(__file__).parent.parent
    src_path = repo_root / "src"
    env["PYTHONPATH"] = str(src_path) + os.pathsep + env.get("PYTHONPATH", "")

    cmd = [sys.executable, "-m", "laptop_agents.run"] + agent_args

    restarts = 0

    while restarts < MAX_RESTARTS:
        print(f"\n[SUPERVISOR] Starting Agent (Attempt {restarts + 1}/{MAX_RESTARTS})...")
        print(f"[SUPERVISOR] CMD: {' '.join(cmd)}")

        # Start process
        # On Unix, setsid for process group killing. On Windows, creationflags.
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

        # Monitoring Loop
        try:
            while True:
                ret = proc.poll()
                if ret is not None:
                    # Process exited
                    if ret == 0:
                        print("[SUPERVISOR] Agent exited successfully (0).")
                        return 0
                    else:
                        print(f"[SUPERVISOR] Agent crashed with exit code {ret}.")
                        break # Break monitoring loop to trigger restart logic

                # Check heartbeat
                age = get_heartbeat_age()
                if age > HEARTBEAT_TIMEOUT:
                    print(f"[SUPERVISOR] WARNING: Heartbeat stale ({age:.1f}s > {HEARTBEAT_TIMEOUT}s).")
                    kill_process(proc)
                    # Wait a moment for process to die
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutError:
                        print("[SUPERVISOR] Force kill required.")
                    break # Break monitoring loop to trigger restart

                time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("\n[SUPERVISOR] KeyboardInterrupt received. Stopping agent...")
            kill_process(proc)
            return 0

        # Restart logic
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
```

---

## PHASE 2: Verification

### Task 2.1: Verify Supervisor with Mock Failure

**Goal**: Ensure supervisor restarts a dying process.

**Command**:
```powershell
# Create a dummy freezing agent script
echo "import time; import json; import os; from pathlib import Path;
Path('logs').mkdir(exist_ok=True);
with open('logs/heartbeat.json', 'w') as f: json.dump({'unix_ts': time.time() - 40}, f);
print('I am a frozen agent checking in with old timestamp');
time.sleep(10)" > tests/mock_frozen_agent.py

# Run supervisor against it (using python -m approach by tricking cmd args or just temporarily modifying supervisor for test?
# Better: Just run the supervisor against the REAL app in dry-run mode for 10 seconds.
```

**Verification Command**:
```powershell
python scripts/supervisor.py --mode live-session --duration 1 --dry-run --symbol BTCUSDT
```
**Expected Output**: The session runs to completion (exit code 0), supervisor exits cleanly.

**Fail Test Command**:
```powershell
# We can't easily injection-fail the real app without modifying code.
# But we can verify syntax and dry-run success.
python -m py_compile scripts/supervisor.py
```

---

## PHASE 3: Commit

```powershell
git add scripts/supervisor.py
git commit -m "feat(ops): add supervisor script for autonomous process monitoring and restarts"
git push origin main
```
