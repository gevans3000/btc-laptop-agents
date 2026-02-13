import logging
import os
import re
from pathlib import Path

SENSITIVE_PATTERNS = [
    r'(?i)(api[_-]?key|secret|password|token|auth)(["\']?\s*[:=]\s*["\']?)[A-Za-z0-9+/=_-]{8,}',
    r"(?i)(Bearer\s+)[A-Za-z0-9+/=_-]{12,}",
]


def scrub_secrets(text: str) -> str:
    out = str(text)
    out = re.sub(SENSITIVE_PATTERNS[0], r"\1\2***", out)
    out = re.sub(SENSITIVE_PATTERNS[1], r"\1***", out)
    return out


class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = scrub_secrets(record.msg)
        return True


def setup_logger(name: str = "btc_alert") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    handler.addFilter(SensitiveDataFilter())
    logger.addHandler(handler)

    log_dir = Path(os.environ.get("BTC_ALERT_LOG_DIR", ".workspace/logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "btc_alert.log")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
    )
    file_handler.addFilter(SensitiveDataFilter())
    logger.addHandler(file_handler)
    return logger


logger = setup_logger()
