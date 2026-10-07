from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from cryptobridge.config import Settings
from cryptobridge.logging_config import configure_logging


def _stream_handlers(root: logging.Logger) -> list[logging.Handler]:
    return [
        handler
        for handler in root.handlers
        if isinstance(handler, logging.StreamHandler)
        and not isinstance(handler, RotatingFileHandler)
    ]


def _file_handlers(root: logging.Logger) -> list[logging.Handler]:
    return [handler for handler in root.handlers if isinstance(handler, RotatingFileHandler)]


def test_configure_logging_file_only(capsys, tmp_path):
    settings = Settings.model_construct(
        log_to_file=True,
        log_dir=str(tmp_path),
        log_file="test.log",
        log_level="INFO",
        log_format="text",
        log_max_bytes=10_485_760,
        log_backup_count=5,
    )
    file_path = configure_logging(settings)
    root = logging.getLogger()

    assert file_path == tmp_path / "test.log"
    assert len(_stream_handlers(root)) == 0
    assert len(_file_handlers(root)) == 1

    marker = "file-only-marker-42"
    logging.getLogger("cryptobridge.test").info(marker)

    captured = capsys.readouterr()
    assert marker not in captured.out
    assert marker in (tmp_path / "test.log").read_text(encoding="utf-8")


def test_configure_logging_console_only(tmp_path):
    settings = Settings.model_construct(
        log_to_file=False,
        log_dir=str(tmp_path),
        log_file="test.log",
        log_level="INFO",
        log_format="text",
        log_max_bytes=10_485_760,
        log_backup_count=5,
    )
    file_path = configure_logging(settings)
    root = logging.getLogger()

    assert file_path is None
    assert len(root.handlers) == 1
    assert len(_stream_handlers(root)) == 1
    assert len(_file_handlers(root)) == 0
    assert not (tmp_path / "test.log").exists()
