"""Unit tests for config.logging — configure_logging + get_logger."""

from __future__ import annotations

import logging

from config.logging import configure_logging, get_logger


class TestConfigureLogging:
    def setup_method(self):
        # Reset root logger handlers to avoid test pollution
        root = logging.getLogger()
        root.handlers.clear()

    def test_adds_handler_to_root_logger(self):
        configure_logging("DEBUG")
        root = logging.getLogger()
        assert len(root.handlers) >= 1

    def test_sets_log_level(self):
        configure_logging("WARNING")
        root = logging.getLogger()
        assert root.level == logging.WARNING

    def test_level_case_insensitive(self):
        configure_logging("debug")
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_handler_writes_to_stdout(self):
        configure_logging("INFO")
        root = logging.getLogger()
        handler = root.handlers[-1]
        assert isinstance(handler, logging.StreamHandler)

    def test_default_level_is_info(self):
        configure_logging()
        root = logging.getLogger()
        assert root.level == logging.INFO


class TestGetLogger:
    def test_returns_bound_logger(self):
        log = get_logger("test.module")
        # structlog BoundLogger has .info, .warning, .error, etc.
        assert callable(getattr(log, "info", None))
        assert callable(getattr(log, "error", None))

    def test_different_names_return_loggers(self):
        log1 = get_logger("module.a")
        log2 = get_logger("module.b")
        # Both should be usable
        assert log1 is not None
        assert log2 is not None
