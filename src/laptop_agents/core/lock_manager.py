import os
import psutil
from pathlib import Path
from typing import Dict, Any
from laptop_agents.core.logger import logger


class LockManager:
    def __init__(self, lock_file: Path) -> None:
        self.lock_file = lock_file

    def _is_our_process(self, proc: psutil.Process) -> bool:
        """
        Best-effort check to avoid blocking on unrelated Python processes if a PID
        gets reused or a stale lock points at a different command.
        """
        try:
            cmdline = proc.cmdline()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

        # Our CLI launches via `python -m laptop_agents ...`
        return any("laptop_agents" in str(arg) for arg in cmdline)

    def acquire(self) -> bool:
        """Acquire the lock. Returns True if successful, False if already locked."""
        if self.lock_file.exists():
            try:
                with open(self.lock_file, "r") as f:
                    content = f.read().strip()
                    if content:
                        old_pid = int(content)
                        if psutil.pid_exists(old_pid):
                            # Check if it's actually a python process (optional but safer)
                            try:
                                proc = psutil.Process(old_pid)
                                if (
                                    "python" in proc.name().lower()
                                    and self._is_our_process(proc)
                                ):
                                    return False
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass
            except (ValueError, Exception) as e:
                logger.warning(f"Error reading lockfile: {e}. Overwriting.")

        # Write current PID
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.lock_file, "w") as f:
            f.write(str(os.getpid()))
        return True

    def release(self) -> None:
        """Release the lock."""
        if self.lock_file.exists():
            try:
                os.remove(self.lock_file)
            except Exception as e:
                logger.error(f"Failed to release lock: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get status of the process associated with the lock."""
        if not self.lock_file.exists():
            return {"running": False}

        try:
            with open(self.lock_file, "r") as f:
                content = f.read().strip()
                if not content:
                    return {"running": False}
                pid = int(content)
                if psutil.pid_exists(pid):
                    proc = psutil.Process(pid)
                    if not self._is_our_process(proc):
                        return {"running": False}
                    return {
                        "running": True,
                        "pid": pid,
                        "created": proc.create_time(),
                        "memory_info": proc.memory_info()._asdict(),
                        "status": proc.status(),
                    }
        except (OSError, ValueError, psutil.Error) as e:
            logger.debug(f"Error getting lock status: {e}")

        return {"running": False}
