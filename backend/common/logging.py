from __future__ import annotations
import logging, json, os, sys, time
from .config import LOG_LEVEL, APP_NAME

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.time(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if hasattr(record, "extra"):
            payload["extra"] = record.extra
        return json.dumps(payload, ensure_ascii=False)

def setup_logging() -> logging.Logger:
    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    logger = logging.getLogger(APP_NAME)
    logger.setLevel(level)
    # Avoid duplicate handlers if called twice
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setLevel(level)
        h.setFormatter(JsonFormatter())
        logger.addHandler(h)
        logger.propagate = False
    return logger
