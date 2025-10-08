import logging
import sys
from typing import Any

import structlog

from app.core.settings import Settings


def configure_logging(settings: Settings) -> None:
    """Configure structlog + stdlib logging with JSON output."""
    logging_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(
        level=logging_level,
        format="%(message)s",
        stream=sys.stdout,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            _add_trace_id_if_missing,
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def _add_trace_id_if_missing(_, __, event_dict: dict[str, Any]) -> dict[str, Any]:
    event_dict.setdefault("trace_id", structlog.contextvars.get_contextvars().get("trace_id"))
    return event_dict
