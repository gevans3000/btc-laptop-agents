import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional

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
             
        return json.dumps(log_entry, separators=(",", ":"))

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
