import json
import logging
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, Optional

SENSITIVE_PATTERNS = [
    r'(?i)(api[_-]?key|secret|password|token|auth)(["\']?\s*[:=]\s*["\']?)[A-Za-z0-9+/=_-]{16,}',
    r'(?i)(Bearer\s+)[A-Za-z0-9+/=_-]{20,}',
]

def scrub_secrets(text: str) -> str:
    """Replace sensitive values with ***."""
    if not isinstance(text, str):
        text = str(text)
    # Also scrub any values from .env
    env_secrets = [v for k, v in os.environ.items() 
                   if any(x in k.upper() for x in ['KEY', 'SECRET', 'TOKEN', 'PASSWORD'])
                   and v and len(v) > 8]
    for secret in env_secrets:
        text = text.replace(secret, '***')
    
    # Process patterns
    text = re.sub(SENSITIVE_PATTERNS[0], r'\1\2***', text)
    text = re.sub(SENSITIVE_PATTERNS[1], r'\1***', text)
    # Specific catch for Bitunix-like keys (alphanumeric 32+)
    text = re.sub(r'\b[a-zA-Z0-9]{32,}\b', '***', text)
    return text


class SensitiveDataFilter(logging.Filter):
    """Filter that scrubs sensitive data from log records."""
    def filter(self, record):
        if record.msg and isinstance(record.msg, str):
            record.msg = scrub_secrets(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: (scrub_secrets(v) if isinstance(v, str) else v) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(scrub_secrets(arg) if isinstance(arg, str) else arg for arg in record.args)
        return True



class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "component": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "meta") and isinstance(record.meta, dict):
            log_entry["meta"] = record.meta
        elif record.args and isinstance(record.args, dict):
             # Support for logger.info("msg", {"extra": "data"}) style if meta not used
             log_entry["meta"] = record.args
             
        return scrub_secrets(json.dumps(log_entry, separators=(",", ":")))

class AutonomousMemoryHandler(logging.Handler):
    """Automatically captures errors into the Learning Debugger memory."""
    def emit(self, record):
        if record.levelno >= logging.ERROR:
            try:
                # Import here to avoid circular imports and ensure it's available
                import sys
                import os
                
                # Find project root (3 levels up from this file)
                current_file_path = os.path.abspath(__file__)
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file_path))))
                scripts_path = os.path.join(project_root, "scripts")
                
                if scripts_path not in sys.path:
                    sys.path.append(scripts_path)
                
                try:
                    import error_fingerprinter
                    error_msg = record.getMessage()
                    if record.exc_info:
                        import traceback
                        error_msg += "\n" + "".join(traceback.format_exception(*record.exc_info))
                    
                    # Silently capture the error
                    error_fingerprinter.capture(error_msg, "NEEDS_DIAGNOSIS", "Auto-captured from logger")
                except ImportError:
                    # If we can't find the scripts, skip silently
                    pass
            except Exception:
                # Never allow a logging error to crash the application
                pass

def setup_logger(name: str = "btc_agents", log_dir: str = "logs"):
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # Create filter
    sensitive_filter = SensitiveDataFilter()

    # JSON File Handler
    json_path = os.path.join(log_dir, "system.jsonl")
    fh = logging.FileHandler(json_path)
    fh.setFormatter(JsonFormatter())
    fh.addFilter(sensitive_filter)
    logger.addHandler(fh)
    
    # Console Handler (Human readable)
    ch = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    ch.addFilter(sensitive_filter)
    logger.addHandler(ch)

    # Autonomous Memory Handler
    mh = AutonomousMemoryHandler()
    mh.setLevel(logging.ERROR)
    mh.addFilter(sensitive_filter)
    logger.addHandler(mh)
    
    return logger

# Singleton-ish instance
logger = setup_logger()

def write_alert(message: str, alert_path: str = "logs/alert.txt"):
    """Write a critical alert to a file and optional Webhook."""
    import os
    import requests
    from datetime import datetime
    
    # 1. Write to file
    try:
        os.makedirs(os.path.dirname(alert_path), exist_ok=True)
        with open(alert_path, "a", encoding="utf-8") as f:
            ts = datetime.now().isoformat()
            f.write(f"[{ts}] {message}\n")
    except Exception as e:
        print(f"Failed to write alert file: {e}")

    # 2. Webhook
    webhook_url = os.environ.get("WEBHOOK_URL")
    if webhook_url:
        try:
            payload = {"content": f"🚨 **CRITICAL ALERT** 🚨\n{message}"}
            # Simple retry
            for _ in range(3):
                r = requests.post(webhook_url, json=payload, timeout=5)
                if r.status_code < 500:
                    break
                time.sleep(1)
        except Exception as e:
             # Don't crash on alert failure
            print(f"Failed to send webhook: {e}")
