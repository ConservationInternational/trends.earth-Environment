"""Tests for the gefcore.loggers module."""

import logging
import os
from unittest.mock import MagicMock, patch

from gefcore import loggers


class TestGEFLogger:
    """Test the custom GEFLogger class."""

    def test_gef_logger_inheritance(self):
        """Test that GEFLogger inherits from logging.Logger."""
        assert issubclass(loggers.GEFLogger, logging.Logger)

    def test_gef_logger_has_send_progress_method(self):
        """Test that GEFLogger has send_progress method."""
        logging.setLoggerClass(loggers.GEFLogger)
        logger = logging.getLogger("test_logger")
        assert hasattr(logger, "send_progress")
        assert callable(logger.send_progress)

    @patch("gefcore.loggers.patch_execution")
    def test_send_progress_in_prod_environment(self, mock_patch_execution):
        """Test send_progress calls API in production environment."""
        # Set production environment
        os.environ["ENV"] = "prod"

        logging.setLoggerClass(loggers.GEFLogger)
        logger = logging.getLogger("test_logger")

        logger.send_progress(50)

        mock_patch_execution.assert_called_once_with(json={"progress": 50})

    def test_send_progress_in_dev_environment(self, capture_logs):
        """Test send_progress logs message in development environment."""
        # Set development environment
        os.environ["ENV"] = "dev"

        logging.setLoggerClass(loggers.GEFLogger)
        logger = logging.getLogger("test_logger")

        # Capture logs
        handler = logging.StreamHandler(capture_logs)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.send_progress(75)

        log_output = capture_logs.getvalue()
        assert "Progress: 75%" in log_output


class TestServerLogHandler:
    """Test the ServerLogHandler class."""

    def test_server_log_handler_inheritance(self):
        """Test that ServerLogHandler inherits from logging.Handler."""
        assert issubclass(loggers.ServerLogHandler, logging.Handler)

    @patch("gefcore.loggers.save_log")
    def test_emit_calls_save_log_api(self, mock_save_log):
        """Test that emit method calls save_log API."""
        handler = loggers.ServerLogHandler()

        # Create a log record
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        handler.emit(record)

        mock_save_log.assert_called_once()
        call_args = mock_save_log.call_args
        assert call_args[1]["json"]["text"] == "Test message"
        assert call_args[1]["json"]["level"] == "INFO"

    @patch("gefcore.loggers.save_log")
    def test_emit_handles_exceptions(self, mock_save_log):
        """Test that emit method handles exceptions gracefully."""
        mock_save_log.side_effect = Exception("API call failed")

        handler = loggers.ServerLogHandler()

        # Mock the handleError method to verify it gets called
        handler.handleError = MagicMock()

        record = logging.LogRecord(
            name="test_logger",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Test error",
            args=(),
            exc_info=None,
        )

        # Should not raise an exception
        handler.emit(record)

        # Verify handleError was called
        handler.handleError.assert_called_once_with(record)


class TestGetLoggerFunction:
    """Test the get_logger function."""

    def test_get_logger_returns_gef_logger_instance(self):
        """Test that get_logger returns a GEFLogger instance."""
        logger = loggers.get_logger("test_logger")
        assert isinstance(logger, loggers.GEFLogger)

    def test_get_logger_sets_debug_level(self):
        """Test that get_logger sets logging level to DEBUG."""
        logger = loggers.get_logger("test_logger")
        assert logger.level == logging.DEBUG

    def test_get_logger_clears_existing_handlers(self):
        """Test that get_logger clears existing handlers."""
        logger = loggers.get_logger("test_logger")

        # Add a handler
        old_handler = logging.StreamHandler()
        logger.addHandler(old_handler)

        # Get logger again
        logger = loggers.get_logger("test_logger")

        # Verify old handler is not in the logger
        assert old_handler not in logger.handlers

    def test_get_logger_in_prod_uses_server_handler(self):
        """Test that get_logger uses ServerLogHandler in production."""
        os.environ["ENV"] = "prod"

        logger = loggers.get_logger("test_logger")

        # Check that one of the handlers is ServerLogHandler
        server_handlers = [
            h for h in logger.handlers if isinstance(h, loggers.ServerLogHandler)
        ]
        assert len(server_handlers) == 1

    def test_get_logger_in_dev_uses_stream_handler(self):
        """Test that get_logger uses StreamHandler in development."""
        os.environ["ENV"] = "dev"

        logger = loggers.get_logger("test_logger")

        # Check that one of the handlers is StreamHandler
        stream_handlers = [
            h for h in logger.handlers if isinstance(h, logging.StreamHandler)
        ]
        assert len(stream_handlers) == 1

    def test_get_logger_with_custom_name(self):
        """Test that get_logger works with custom logger names."""
        logger = loggers.get_logger("custom_logger_name")
        assert logger.name == "custom_logger_name"

    def test_get_logger_without_name_uses_default(self):
        """Test that get_logger uses default name when none provided."""
        logger = loggers.get_logger()
        assert logger.name == "gefcore"

    def test_logger_formatter_in_prod(self):
        """Test logger formatter configuration in production."""
        os.environ["ENV"] = "prod"

        logger = loggers.get_logger("test_logger")

        server_handlers = [
            h for h in logger.handlers if isinstance(h, loggers.ServerLogHandler)
        ]
        assert len(server_handlers) == 1

        formatter = server_handlers[0].formatter
        assert formatter is not None
        assert formatter._fmt == "%(message)s"

    def test_logger_formatter_in_dev(self):
        """Test logger formatter configuration in development."""
        os.environ["ENV"] = "dev"

        logger = loggers.get_logger("test_logger")

        stream_handlers = [
            h for h in logger.handlers if isinstance(h, logging.StreamHandler)
        ]
        assert len(stream_handlers) == 1

        formatter = stream_handlers[0].formatter
        assert formatter is not None
        expected_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        assert formatter._fmt == expected_format

    def test_multiple_get_logger_calls_same_instance(self):
        """Test that multiple calls to get_logger with same name return same instance."""
        logger1 = loggers.get_logger("same_name")
        logger2 = loggers.get_logger("same_name")

        assert logger1 is logger2


class TestLoggerIntegration:
    """Integration tests for the logger functionality."""

    def test_logger_can_log_messages(self, capture_logs):
        """Test that logger can actually log messages."""
        os.environ["ENV"] = "dev"

        logger = loggers.get_logger("integration_test")

        # Add our capture handler
        handler = logging.StreamHandler(capture_logs)
        logger.addHandler(handler)

        logger.info("Test info message")
        logger.error("Test error message")
        logger.debug("Test debug message")

        log_output = capture_logs.getvalue()
        assert "Test info message" in log_output
        assert "Test error message" in log_output
        assert "Test debug message" in log_output

    @patch("gefcore.loggers.patch_execution")
    @patch("gefcore.loggers.save_log")
    def test_logger_integration_with_api_calls(
        self, mock_save_log, mock_patch_execution
    ):
        """Test logger integration with API calls in production."""
        os.environ["ENV"] = "prod"

        logger = loggers.get_logger("integration_test")

        # Test send_progress
        logger.send_progress(25)
        mock_patch_execution.assert_called_with(json={"progress": 25})

        # Test regular logging (should call save_log through ServerLogHandler)
        logger.info("Integration test message")

        # Verify save_log was called
        assert mock_save_log.called
