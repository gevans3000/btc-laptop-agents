import json
import time
import os
import sys
from pathlib import Path

# Config
HEARTBEAT_PATH = Path("logs/heartbeat.json")
MAX_AGE_SEC = 5.0
CHECK_INTERVAL = 1.0

def monitor():
    """
    Monitors the heartbeat file and alerts if it becomes stale.
    This runs in a separate process to detect freezes in the main trading engine.
    """
    print(f"=== HEARTBEAT WATCHDOG STARTED ===")
    print(f"Target: {HEARTBEAT_PATH.absolute()}")
    print(f"Max Age: {MAX_AGE_SEC}s")
    
    consecutive_stale = 0
    
    while True:
        try:
            if not HEARTBEAT_PATH.exists():
                print(f"[{time.strftime('%H:%M:%S')}] WARNING: Heartbeat file missing")
            else:
                # Check file modification time as a backup
                mtime = os.path.getmtime(HEARTBEAT_PATH)
                file_age = time.time() - mtime
                
                with open(HEARTBEAT_PATH, "r") as f:
                    try:
                        data = json.load(f)
                        last_ts = data.get("last_updated_ts") or data.get("unix_ts") or mtime
                    except json.JSONDecodeError:
                        last_ts = mtime # Fallback to file system time
                
                age = time.time() - last_ts
                
                # We use the max of file system age and internal timestamp age
                effective_age = max(age, file_age)
                
                if effective_age > MAX_AGE_SEC:
                    consecutive_stale += 1
                    print(f"[{time.strftime('%H:%M:%S')}] ALERT: Heartbeat STALE ({effective_age:.1f}s)")
                    if consecutive_stale >= 3:
                        print(f"[{time.strftime('%H:%M:%S')}] CRITICAL: Process likely FROZEN.")
                else:
                    if consecutive_stale > 0:
                        print(f"[{time.strftime('%H:%M:%S')}] RECOVERED: Heartbeat is back (Age: {effective_age:.1f}s)")
                    consecutive_stale = 0
                    
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] MONITOR ERROR: {e}")
            
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    try:
        monitor()
    except KeyboardInterrupt:
        print("\nWatcher stopped.")
