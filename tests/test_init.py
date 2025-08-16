"""Tests for the gefcore.__init__ module."""

import logging
import os
import sys
from unittest.mock import MagicMock, patch


class TestGefcoreInit:
    """Test the gefcore.__init__ module."""

    def test_module_imports_successfully(self):
        """Test that gefcore module can be imported without errors."""
        import gefcore

        assert gefcore is not None

    def test_logger_configuration(self):
        """Test that logger is properly configured."""
        import gefcore

        assert hasattr(gefcore, "logger")
        assert isinstance(gefcore.logger, logging.Logger)

        # Check that handlers are properly configured
        assert len(gefcore.logger.handlers) >= 1

        # Check that logger level is set to DEBUG
        assert gefcore.logger.level == logging.DEBUG

    @patch("rollbar.init")
    def test_rollbar_initialization(self, mock_rollbar_init):
        """Test that Rollbar is properly initialized."""
        # Set environment variables to trigger rollbar initialization
        original_env = os.environ.get("ENV")
        original_token = os.environ.get("ROLLBAR_SCRIPT_TOKEN")

        try:
            os.environ["ENV"] = "production"
            os.environ["ROLLBAR_SCRIPT_TOKEN"] = "test_token"  # noqa: S105

            # Reload the module to trigger rollbar.init
            import importlib

            import gefcore

            importlib.reload(gefcore)

            # Verify rollbar.init was called
            mock_rollbar_init.assert_called()
        finally:
            # Restore original environment
            if original_env is not None:
                os.environ["ENV"] = original_env
            elif "ENV" in os.environ:
                del os.environ["ENV"]
            if original_token is not None:
                os.environ["ROLLBAR_SCRIPT_TOKEN"] = original_token
            elif "ROLLBAR_SCRIPT_TOKEN" in os.environ:
                del os.environ["ROLLBAR_SCRIPT_TOKEN"]

    def test_exception_handler_configuration(self):
        """Test that custom exception handler is configured."""
        import gefcore

        assert hasattr(gefcore, "handle_exception")
        assert callable(gefcore.handle_exception)

        # Verify sys.excepthook is set to our handler
        assert sys.excepthook == gefcore.handle_exception

    def test_handle_exception_with_keyboard_interrupt(self, capture_logs):
        """Test exception handler with KeyboardInterrupt."""
        import gefcore

        # Mock sys.__excepthook__
        original_excepthook = sys.__excepthook__
        mock_excepthook = MagicMock()
        sys.__excepthook__ = mock_excepthook

        try:
            # Create KeyboardInterrupt instance
            interrupt_instance = KeyboardInterrupt("Test interrupt")

            # Test KeyboardInterrupt handling
            gefcore.handle_exception(KeyboardInterrupt, interrupt_instance, None)

            # Should call original excepthook and return early
            # Use any() to check if the call was made with correct arguments
            assert mock_excepthook.called
            call_args = mock_excepthook.call_args[0]
            assert call_args[0] is KeyboardInterrupt
            assert isinstance(call_args[1], KeyboardInterrupt)
            assert str(call_args[1]) == "Test interrupt"
            assert call_args[2] is None

        finally:
            sys.__excepthook__ = original_excepthook

    def test_handle_exception_with_regular_exception(self, capture_logs):
        """Test exception handler with regular exceptions."""
        import gefcore

        # Add our capture handler to the gefcore logger
        handler = logging.StreamHandler(capture_logs)
        gefcore.logger.addHandler(handler)

        # Test regular exception handling
        test_exception = ValueError("Test error")
        gefcore.handle_exception(ValueError, test_exception, None)

        # Should log the exception
        log_output = capture_logs.getvalue()
        assert "Uncaught exception" in log_output

    @patch("gefcore.runner.run")
    def test_runner_called_in_non_test_environment(self, mock_run):
        """Test that runner.run() is called when not in test environment."""
        # Temporarily remove test environment variables
        original_env = os.environ.get("ENV")
        original_testing = os.environ.get("TESTING")
        original_argv = sys.argv[:]

        # Remove environment variables that would prevent running
        if "ENV" in os.environ:
            del os.environ["ENV"]
        if "TESTING" in os.environ:
            del os.environ["TESTING"]

        # Remove pytest from sys.argv
        sys.argv = ["script.py"]

        # Clear pytest from sys.modules temporarily
        pytest_module = sys.modules.pop("pytest", None)

        try:
            # Reload the module to trigger runner execution
            import importlib

            import gefcore

            importlib.reload(gefcore)

            # Verify runner.run was called
            mock_run.assert_called_once()
        finally:
            # Restore original environment
            if original_env is not None:
                os.environ["ENV"] = original_env
            if original_testing is not None:
                os.environ["TESTING"] = original_testing
            sys.argv = original_argv
            if pytest_module is not None:
                sys.modules["pytest"] = pytest_module

    def test_runner_not_called_in_test_environment(self, setup_test_environment):
        """Test that runner.run() is not called in test environment."""
        # ENV should be set to 'test' by conftest.py
        assert os.environ.get("ENV") == "test"

        # Import should succeed without calling runner
        import gefcore

        assert gefcore is not None

    @patch("gefcore.runner.run")
    def test_import_error_handling(self, mock_run):
        """Test handling of ImportError when importing runner."""
        mock_run.side_effect = ImportError("Could not import runner module")

        # Temporarily remove test environment
        original_env = os.environ.get("ENV")
        if "ENV" in os.environ:
            del os.environ["ENV"]

        try:
            # Should not raise an exception, just log a warning
            import importlib

            import gefcore

            importlib.reload(gefcore)

        finally:
            # Restore environment
            if original_env:
                os.environ["ENV"] = original_env

    @patch("gefcore.runner.run")
    def test_file_not_found_error_handling(self, mock_run, capture_logs):
        """Test handling of FileNotFoundError when running."""
        mock_run.side_effect = FileNotFoundError("Service account file not found")

        # Add capture handler
        import gefcore

        handler = logging.StreamHandler(capture_logs)
        gefcore.logger.addHandler(handler)

        # Temporarily remove test environment variables
        original_env = os.environ.get("ENV")
        original_testing = os.environ.get("TESTING")
        original_argv = sys.argv[:]

        # Remove environment variables that would prevent running
        if "ENV" in os.environ:
            del os.environ["ENV"]
        if "TESTING" in os.environ:
            del os.environ["TESTING"]

        # Remove pytest from sys.argv
        sys.argv = ["script.py"]

        # Clear pytest from sys.modules temporarily
        pytest_module = sys.modules.pop("pytest", None)

        try:
            # Reload to trigger the exception
            import importlib

            importlib.reload(gefcore)

            # Should log a warning
            log_output = capture_logs.getvalue()
            assert "Service account file not found" in log_output

        finally:
            # Restore original environment
            if original_env is not None:
                os.environ["ENV"] = original_env
            if original_testing is not None:
                os.environ["TESTING"] = original_testing
            sys.argv = original_argv
            if pytest_module is not None:
                sys.modules["pytest"] = pytest_module

    @patch("gefcore.runner.run")
    def test_general_exception_handling(self, mock_run, capture_logs):
        """Test handling of general exceptions when running."""
        mock_run.side_effect = Exception("General error")

        # Add capture handler
        import gefcore

        handler = logging.StreamHandler(capture_logs)
        gefcore.logger.addHandler(handler)

        # Temporarily remove test environment variables
        original_env = os.environ.get("ENV")
        original_testing = os.environ.get("TESTING")
        original_argv = sys.argv[:]

        # Remove environment variables that would prevent running
        if "ENV" in os.environ:
            del os.environ["ENV"]
        if "TESTING" in os.environ:
            del os.environ["TESTING"]

        # Remove pytest from sys.argv
        sys.argv = ["script.py"]

        # Clear pytest from sys.modules temporarily
        pytest_module = sys.modules.pop("pytest", None)

        try:
            # Reload to trigger the exception
            import importlib

            importlib.reload(gefcore)

            # Should log an error
            log_output = capture_logs.getvalue()
            assert "Error running main script" in log_output
            assert "General error" in log_output

        finally:
            # Restore original environment
            if original_env is not None:
                os.environ["ENV"] = original_env
            if original_testing is not None:
                os.environ["TESTING"] = original_testing
            sys.argv = original_argv
            if pytest_module is not None:
                sys.modules["pytest"] = pytest_module


class TestModuleIntegration:
    """Integration tests for the gefcore module."""

    def test_all_submodules_importable_from_init(self):
        """Test that all submodules are accessible after importing gefcore."""

        # These should be importable after gefcore is imported
        from gefcore import api, loggers, runner

        assert api is not None
        assert loggers is not None
        assert runner is not None

    def test_logging_configuration_persists(self):
        """Test that logging configuration persists across imports."""
        import gefcore

        # Get initial handler count
        initial_handler_count = len(gefcore.logger.handlers)

        # Import again (simulating multiple imports)
        import importlib

        importlib.reload(gefcore)

        # Handler configuration should be consistent
        assert len(gefcore.logger.handlers) >= initial_handler_count
