import json
import logging
from datetime import datetime, timezone

from app.core.config import settings
from app.core.request_context import current_request_id


_original_record_factory = logging.getLogRecordFactory()


def _record_factory(*args, **kwargs):
    record = _original_record_factory(*args, **kwargs)
    record.request_id = current_request_id() or "-"
    return record


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        for key in ("method", "path", "status_code", "duration_ms", "client", "event"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    logging.setLogRecordFactory(_record_factory)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level)

