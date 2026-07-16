import json
import logging
import logging.config
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class MaxLevelFilter(logging.Filter):
    def __init__(self, max_level: int = logging.WARNING):
        super().__init__()
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= self.max_level


def configure_logging(level: str) -> None:
    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"json": {"()": "app.core.logging_config.JsonFormatter"}},
        "filters": {"through_warning": {"()": "app.core.logging_config.MaxLevelFilter"}},
        "handlers": {
            "application": {"class": "logging.StreamHandler", "formatter": "json", "filters": ["through_warning"], "stream": "ext://sys.stdout"},
            "error": {"class": "logging.StreamHandler", "formatter": "json", "stream": "ext://sys.stderr", "level": "ERROR"},
        },
        "root": {"handlers": ["application", "error"], "level": level},
        "loggers": {
            "uvicorn.access": {"handlers": ["application"], "level": level, "propagate": False},
            "uvicorn.error": {"handlers": ["application", "error"], "level": level, "propagate": False},
            "hiop.security": {"handlers": ["application", "error"], "level": "INFO", "propagate": False},
        },
    })
