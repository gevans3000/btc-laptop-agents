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
    # Also scrub any values from .env
    env_secrets = [v for k, v in os.environ.items() 
                   if any(x in k.upper() for x in ['KEY', 'SECRET', 'TOKEN', 'PASSWORD'])
                   and v and len(v) > 8]
    for secret in env_secrets:
        text = text.replace(secret, '***')
    
    # Process patterns
    text = re.sub(SENSITIVE_PATTERNS[0], r'\1\2***', text)
    text = re.sub(SENSITIVE_PATTERNS[1], r'\1***', text)
    return text


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

def setup_logger(name: str = "btc_agents", log_dir: str = "logs"):
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # JSON File Handler
    json_path = os.path.join(log_dir, "system.jsonl")
    fh = logging.FileHandler(json_path)
    fh.setFormatter(JsonFormatter())
    logger.addHandler(fh)
    
    # Console Handler (Human readable)
    ch = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    
    return logger

# Singleton-ish instance
logger = setup_logger()

def write_alert(message: str, alert_path: str = "logs/alert.txt"):
    """Write a critical alert to a file for external monitoring."""
    import os
    from datetime import datetime
    
    os.makedirs(os.path.dirname(alert_path), exist_ok=True)
    with open(alert_path, "a", encoding="utf-8") as f:
        ts = datetime.now().isoformat()
        f.write(f"[{ts}] {message}\n")
