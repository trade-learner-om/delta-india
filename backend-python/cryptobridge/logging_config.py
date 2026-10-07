"""Application logging: rotating local file by default, optional console."""

from __future__ import annotations

import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cryptobridge.config import Settings

TEXT_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def _resolve_level(level_name: str) -> int:
    return getattr(logging, str(level_name).upper(), logging.INFO)


def _build_formatter(log_format: str) -> logging.Formatter:
    if str(log_format).lower() == "json":
        return _JsonFormatter()
    return logging.Formatter(TEXT_LOG_FORMAT)


def configure_logging(settings: Settings) -> Path | None:
    """Attach file and/or console handlers from settings."""
    level = _resolve_level(settings.log_level)
    formatter = _build_formatter(settings.log_format)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    file_path: Path | None = None
    if settings.log_to_file:
        log_dir = Path(settings.log_dir).expanduser().resolve()
        log_dir.mkdir(parents=True, exist_ok=True)
        file_path = log_dir / settings.log_file
        file_handler = RotatingFileHandler(
            file_path,
            maxBytes=int(settings.log_max_bytes),
            backupCount=int(settings.log_backup_count),
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        root.addHandler(file_handler)
    else:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(level)
        root.addHandler(stream_handler)

    cryptobridge_logger = logging.getLogger("cryptobridge")
    cryptobridge_logger.setLevel(level)

    if level > logging.DEBUG:
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("websockets").setLevel(logging.WARNING)

    startup_logger = logging.getLogger("cryptobridge.logging")
    if file_path is not None:
        startup_logger.info("Logging to %s", file_path)
    else:
        startup_logger.info("Logging to console only (LOG_TO_FILE=false)")

    return file_path
