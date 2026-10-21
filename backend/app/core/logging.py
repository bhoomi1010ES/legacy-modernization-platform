"""Structured logging with automated sensitive field redaction."""

import json
import logging
import re
from typing import Any

SENSITIVE_KEY_PATTERNS = [
    re.compile(r"pass(word|phrase)?", re.IGNORECASE),
    re.compile(r"secret(_key)?", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"session(_id)?", re.IGNORECASE),
    re.compile(r"api[_-]?key", re.IGNORECASE),
    re.compile(r"auth(orization)?", re.IGNORECASE),
    re.compile(r"cookie", re.IGNORECASE),
]

REDACTED_VALUE = "[REDACTED]"


def redact_sensitive_data(obj: Any) -> Any:
    """Recursively redacts sensitive keys from dictionaries, lists, and strings."""
    if isinstance(obj, dict):
        redacted = {}
        for k, v in obj.items():
            if any(pattern.search(str(k)) for pattern in SENSITIVE_KEY_PATTERNS):
                redacted[k] = REDACTED_VALUE
            else:
                redacted[k] = redact_sensitive_data(v)
        return redacted
    elif isinstance(obj, (list, tuple, set)):
        return [redact_sensitive_data(item) for item in obj]
    elif isinstance(obj, str):
        # Redact bearer tokens or basic auth patterns in raw strings if present
        if "Bearer " in obj:
            return re.sub(r"Bearer\s+[\w\.\-]+", "Bearer [REDACTED]", obj)
        return obj
    return obj


class RedactingJsonFormatter(logging.Formatter):
    """Logging formatter that emits JSON logs with sensitive values masked."""

    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Redact custom extra attributes
        for key, val in record.__dict__.items():
            if key not in ("args", "asctime", "created", "exc_info", "exc_text", "filename",
                           "funcName", "id", "levelname", "levelno", "lineno", "module",
                           "msecs", "message", "msg", "name", "pathname", "process",
                           "processName", "relativeCreated", "stack_info", "thread", "threadName"):
                log_record[key] = redact_sensitive_data(val)

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(redact_sensitive_data(log_record))


def setup_logging(level: str = "INFO"):
    """Initializes root application logger with the redacting formatter."""
    logger = logging.getLogger("rebase")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    handler = logging.StreamHandler()
    handler.setFormatter(RedactingJsonFormatter())

    # Avoid duplicate handlers
    if not logger.handlers:
        logger.addHandler(handler)

    return logger


logger = setup_logging()
