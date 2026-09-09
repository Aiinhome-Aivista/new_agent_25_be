import logging
import json
import time
from datetime import datetime
from typing import Any, Dict

class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "service": "ai-code-review-agent",
            "message": record.getMessage(),
            "logger": record.name
        }
        if hasattr(record, "session_id"):
            log_obj["session_id"] = record.session_id
        if hasattr(record, "duration_ms"):
            log_obj["duration_ms"] = record.duration_ms
        if hasattr(record, "event"):
            log_obj["event"] = record.event
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
    return logger

logger = get_logger("ai_code_review")
