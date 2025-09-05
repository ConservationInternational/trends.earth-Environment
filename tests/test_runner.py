"""Tests for the gefcore.runner module."""

import logging
import os
from unittest.mock import MagicMock, patch

import pytest

from gefcore import runner


class TestRunnerModule:
    """Test the runner module functionality."""

    def test_module_imports_successfully(self):
        """Test that the runner module can be imported without errors."""
        # If we got here, the import succeeded
        assert hasattr(runner, "run")
        assert hasattr(runner, "initialize_earth_engine")
        assert hasattr(runner, "change_status_ticket")
        assert hasattr(runner, "send_result")

    def test_module_constants_are_set(self):
        """Test that module constants are properly set."""
        assert hasattr(runner, "PROJECT_DIR")
        assert hasattr(runner, "ENV")
        assert hasattr(runner, "GOOGLE_PROJECT_ID")
        assert hasattr(runner, "GEE_ENDPOINT")


class TestInitializeEarthEngine:
    """Test the initialize_earth_engine function."""

    def test_initialize_earth_engine_service_account_not_found(self):
        """Test initialization fails when no credentials are available."""
        with pytest.raises(RuntimeError, match="No Google Earth Engine credentials available"):
            runner.initialize_earth_engine()

    @patch("gefcore.runner._has_service_account_file")
    @patch("gefcore.runner._initialize_ee_with_service_account")
    def test_initialize_earth_engine_success(
        self, mock_init_service_account, mock_has_service_account
    ):
        """Test successful Earth Engine initialization."""
        # Mock that service account file exists and initialization succeeds
        mock_has_service_account.return_value = True
        mock_init_service_account.return_value = True

        # Test - should not raise any exception
        runner.initialize_earth_engine()

        # Verify service account initialization was called
        mock_init_service_account.assert_called_once()

    @patch("gefcore.runner._has_service_account_file")
    @patch("gefcore.runner._initialize_ee_with_service_account")
    def test_initialize_earth_engine_credential_error(
        self, mock_init_service_account, mock_has_service_account
    ):
        """Test initialization handles credential errors gracefully."""
        # Mock that service account file exists but initialization fails
        mock_has_service_account.return_value = True
        mock_init_service_account.return_value = False

        with pytest.raises(RuntimeError, match="No Google Earth Engine credentials available"):
            runner.initialize_earth_engine()

    @patch("rollbar.report_message")
    def test_initialize_earth_engine_reports_to_rollbar(self, mock_rollbar_report):
        """Test that missing credentials are reported to Rollbar."""
        with pytest.raises(RuntimeError):
            runner.initialize_earth_engine()

        mock_rollbar_report.assert_called_once_with(
            "Missing GEE credentials",
            extra_data={
                "oauth_available": False,
                "service_account_available": False
            },
        )


class TestStatusAndResultFunctions:
    """Test status and result management functions."""

    @patch("gefcore.runner.patch_execution")
    @patch.object(runner, "ENV", "prod")
    def test_change_status_ticket_prod_environment(self, mock_patch_execution):
        """Test status change in production environment."""
        runner.change_status_ticket("RUNNING")

        mock_patch_execution.assert_called_once_with(json={"status": "RUNNING"})

    @patch.object(runner, "ENV", "dev")
    def test_change_status_ticket_dev_environment(self, capture_logs):
        """Test status change in development environment."""
        # Clear the capture logs to start fresh
        capture_logs.seek(0)
        capture_logs.truncate(0)

        # Test the function call
        runner.change_status_ticket("RUNNING")

        # Check that the appropriate log message was generated
        log_output = capture_logs.getvalue()
        assert "Changing to RUNNING" in log_output

    @patch("gefcore.runner.patch_execution")
    @patch.object(runner, "ENV", "prod")
    def test_send_result_prod_environment(self, mock_patch_execution):
        """Test sending results in production environment."""
        test_results = {"output": "test_data", "success": True}
        runner.send_result(test_results)

        expected_payload = {"results": test_results, "status": "FINISHED"}
        mock_patch_execution.assert_called_once_with(json=expected_payload)

    @patch.object(runner, "ENV", "dev")
    def test_send_result_dev_environment(self, capture_logs):
        """Test sending results in development environment."""
        # Clear the capture logs to start fresh
        capture_logs.seek(0)
        capture_logs.truncate(0)

        test_results = {"output": "test_data", "success": True}
        runner.send_result(test_results)

        log_output = capture_logs.getvalue()
        assert "Finished -> Results:" in log_output
        assert "test_data" in log_output


class TestRunFunction:
    """Test the main run function."""

    @patch("gefcore.runner.initialize_earth_engine")
    @patch("gefcore.runner.change_status_ticket")
    @patch("gefcore.runner.get_params")
    @patch("gefcore.runner.send_result")
    @patch("gefcore.runner.main")
    @patch("gefcore.runner.get_logger")
    def test_run_success_flow(
        self,
        mock_get_logger,
        mock_main,
        mock_send_result,
        mock_get_params,
        mock_change_status,
        mock_init_ee,
    ):
        """Test successful execution flow of run function."""
        # Setup mocks
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        mock_get_params.return_value = {"param1": "value1"}
        mock_main.run.return_value = {"result": "success"}

        # Test
        runner.run()

        # Verify execution order and calls
        mock_init_ee.assert_called_once()
        mock_change_status.assert_called_with("RUNNING")
        mock_get_params.assert_called_once()

        # Verify main was called with correct parameters
        expected_params = {
            "param1": "value1",
            "ENV": os.getenv("ENV"),
            "EXECUTION_ID": os.getenv("EXECUTION_ID"),
        }
        mock_main.run.assert_called_once_with(expected_params, mock_logger)
        mock_send_result.assert_called_once_with({"result": "success"})

    @patch("gefcore.runner.initialize_earth_engine")
    @patch("gefcore.runner.change_status_ticket")
    @patch("gefcore.runner.get_logger")
    @patch("rollbar.report_exc_info")
    def test_run_handles_earth_engine_initialization_error(
        self, mock_rollbar, mock_get_logger, mock_change_status, mock_init_ee
    ):
        """Test run function handles Earth Engine initialization errors."""
        # Setup mocks
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        mock_init_ee.side_effect = Exception("EE initialization failed")

        # Test
        with pytest.raises(Exception, match="EE initialization failed"):
            runner.run()

        # Verify error handling
        mock_change_status.assert_called_with("FAILED")
        mock_rollbar.assert_called_once()

    @patch("gefcore.runner.initialize_earth_engine")
    @patch("gefcore.runner.change_status_ticket")
    @patch("gefcore.runner.get_params")
    @patch("gefcore.runner.get_logger")
    @patch("rollbar.report_exc_info")
    def test_run_handles_missing_main_module(
        self,
        mock_rollbar,
        mock_get_logger,
        mock_get_params,
        mock_change_status,
        mock_init_ee,
    ):
        """Test run function handles missing main script module."""
        # Setup - simulate missing main module
        with patch.object(runner, "main", None):
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            mock_get_params.return_value = {}

            # Test
            with pytest.raises(
                ImportError, match="gefcore.script.main module not found"
            ):
                runner.run()

            # Verify error handling
            mock_change_status.assert_called_with("FAILED")
            mock_rollbar.assert_called_once()

    @patch("gefcore.runner.initialize_earth_engine")
    @patch("gefcore.runner.change_status_ticket")
    @patch("gefcore.runner.get_params")
    @patch("gefcore.runner.main")
    @patch("gefcore.runner.get_logger")
    @patch("rollbar.report_exc_info")
    def test_run_handles_main_script_error(
        self,
        mock_rollbar,
        mock_get_logger,
        mock_main,
        mock_get_params,
        mock_change_status,
        mock_init_ee,
    ):
        """Test run function handles errors in main script execution."""
        # Setup mocks
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        mock_get_params.return_value = {}
        mock_main.run.side_effect = Exception("Script execution failed")

        # Test
        with pytest.raises(Exception, match="Script execution failed"):
            runner.run()

        # Verify error handling
        mock_change_status.assert_called_with("FAILED")
        mock_logger.error.assert_called_with("Script execution failed")
        mock_rollbar.assert_called_once()

    @patch("gefcore.runner.initialize_earth_engine")
    @patch("gefcore.runner.change_status_ticket")
    @patch("gefcore.runner.get_params")
    @patch("gefcore.runner.send_result")
    @patch("gefcore.runner.main")
    @patch("gefcore.runner.get_logger")
    def test_run_passes_environment_variables_to_main(
        self,
        mock_get_logger,
        mock_main,
        mock_send_result,
        mock_get_params,
        mock_change_status,
        mock_init_ee,
    ):
        """Test that run function passes environment variables to main script."""
        # Setup
        os.environ["EXECUTION_ID"] = "test_execution_123"
        os.environ["ENV"] = "test"

        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        mock_get_params.return_value = {"script_param": "value"}
        mock_main.run.return_value = {"result": "test"}

        # Test
        runner.run()

        # Verify environment variables were passed to main
        call_args = mock_main.run.call_args[0][0]  # First argument (params)
        assert call_args["ENV"] == "test"
        assert call_args["EXECUTION_ID"] == "test_execution_123"
        assert call_args["script_param"] == "value"


class TestRunnerLogging:
    """Test logging configuration in runner module."""

    def test_logging_levels_configured(self):
        """Test that logging levels are properly configured for external libraries."""
        # Check that external library loggers are set to ERROR level
        assert logging.getLogger("googleapiclient").level >= logging.ERROR
        assert logging.getLogger("urllib3").level >= logging.ERROR
        assert logging.getLogger("google_auth_httplib2").level >= logging.ERROR
