import logging

from app.core.config import settings
from app.core.request_context import current_request_id


_original_record_factory = logging.getLogRecordFactory()


def _record_factory(*args, **kwargs):
    record = _original_record_factory(*args, **kwargs)
    record.request_id = current_request_id() or "-"
    return record


def configure_logging() -> None:
    logging.setLogRecordFactory(_record_factory)
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s [%(name)s] [request_id=%(request_id)s] %(message)s",
    )

