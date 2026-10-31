"""Structured Application Logging Module.

Provides centralized structured logging for asynchronous FastAPI
applications using Structlog and Python's standard logging system.

Features:
    - Human-readable terminal output.
    - JSON-formatted rotating file logs.
    - UTC ISO-8601 timestamps.
    - Source filename and line-number information.
    - Thread-safe, idempotent initialization.
    - Integration with FastAPI, Uvicorn, and third-party loggers.
"""

import json
import logging
import logging.handlers
import sys
import threading
from pathlib import Path
from typing import Any

import structlog

from forecasting_analytics.config.settings import get_settings


class LoggingLifecycle:
    """Manage the process-local logging configuration lifecycle."""

    _lock = threading.RLock()
    _is_configured = False

    @classmethod
    def is_configured(cls) -> bool:
        """Return whether logging has been configured."""
        return cls._is_configured

    @classmethod
    def mark_configured(cls) -> None:
        """Mark logging as successfully configured."""
        cls._is_configured = True


def _add_callsite_to_message(
    logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Prefix the event message with its source filename and line number."""
    del logger, method_name

    filename = event_dict.pop("filename", "unknown")
    lineno = event_dict.pop("lineno", 0)

    event = event_dict.get("event", "")

    event_dict["event"] = f"{filename}:{lineno} - {event}"

    return event_dict


def _get_shared_processors() -> list[Any]:
    """Build the shared processing pipeline for all log records."""
    return [
        structlog.processors.CallsiteParameterAdder(
            {
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.LINENO,
            }
        ),
        _add_callsite_to_message,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(
            fmt="iso",
            utc=True,
        ),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]


def _format_console_value(value: Any) -> str:
    """Format a value for human-readable console output."""
    if isinstance(value, str):
        return repr(value) if any(char.isspace() for char in value) else value

    return str(value)


def _render_console(
    logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> str:
    """Render structured events in the requested terminal format."""
    del logger, method_name

    timestamp = event_dict.pop("timestamp", "")
    level = str(event_dict.pop("level", "info")).lower()
    event = event_dict.pop("event", "")

    remaining = " ".join(
        f"{key}={_format_console_value(value)}" for key, value in event_dict.items()
    )

    message = f"{timestamp} [{level:<8}] {event}"

    if remaining:
        message = f"{message} {remaining}"

    return message


def _build_formatter(
    shared_processors: list[Any],
    renderer: Any,
) -> structlog.stdlib.ProcessorFormatter:
    """Create a formatter shared by Structlog and standard logging."""
    return structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )


def _get_log_level() -> int:
    """Resolve the configured logging level."""
    settings = get_settings()

    level = settings.LOG_LEVEL

    if hasattr(level, "value"):
        level = level.value

    return getattr(logging, str(level).upper(), logging.INFO)


def _get_console_renderer() -> Any:
    """Return the environment-appropriate console renderer."""
    settings = get_settings()

    environment = settings.ENVIRONMENT

    if hasattr(environment, "value"):
        environment = environment.value

    if str(environment).upper() in {"STAGING", "PRODUCTION"}:
        return _render_console

    return _render_console


def configure_logging(*, force: bool = False) -> None:
    """Configure application-wide structured logging.

    Parameters
    ----------
    force : bool
        Reconfigure logging even if it has already been configured.
    """
    if LoggingLifecycle.is_configured() and not force:
        return

    with LoggingLifecycle._lock:
        if LoggingLifecycle.is_configured() and not force:
            return

        settings = get_settings()

        logs_dir = Path(settings.LOGS_DIR)
        logs_dir.mkdir(parents=True, exist_ok=True)

        shared_processors = _get_shared_processors()

        # Configure Structlog.
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

        # Create console handler.
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(_get_log_level())
        console_handler.setFormatter(
            _build_formatter(
                shared_processors,
                _get_console_renderer(),
            )
        )

        # Create rotating JSON file handler.
        file_handler = logging.handlers.RotatingFileHandler(
            filename=logs_dir / "app.log",
            mode="a",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(_get_log_level())
        file_handler.setFormatter(
            _build_formatter(
                shared_processors,
                structlog.processors.JSONRenderer(
                    serializer=json.dumps,
                    ensure_ascii=False,
                ),
            )
        )

        # Mark handlers as application-owned.
        console_handler._application_logging_handler = True  # ty: ignore[unresolved-attribute]
        file_handler._application_logging_handler = True  # ty: ignore[unresolved-attribute]

        # Configure the root logger.
        root_logger = logging.getLogger()

        for handler in root_logger.handlers[:]:
            if getattr(
                handler,
                "_application_logging_handler",
                False,
            ):
                root_logger.removeHandler(handler)
                handler.close()

        root_logger.setLevel(_get_log_level())
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)

        # Route Uvicorn and FastAPI logs through the root logger.
        for logger_name in (
            "uvicorn",
            "uvicorn.access",
            "uvicorn.error",
            "fastapi",
        ):
            third_party_logger = logging.getLogger(logger_name)

            third_party_logger.handlers.clear()
            third_party_logger.propagate = True

        # Capture warnings through the logging system.
        logging.captureWarnings(True)

        LoggingLifecycle.mark_configured()


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a configured application logger.

    Parameters
    ----------
    name : str | None
        Optional logger name. Defaults to the configured application name.

    Returns
    -------
        A configured Structlog bound logger.
    """
    if not LoggingLifecycle.is_configured():
        configure_logging()

    settings = get_settings()
    logger_name = name or settings.LOGGER_NAME

    return structlog.get_logger(logger_name)
