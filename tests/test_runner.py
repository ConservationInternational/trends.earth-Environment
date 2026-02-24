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
        with pytest.raises(
            RuntimeError, match="No Google Earth Engine credentials available"
        ):
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

        with pytest.raises(
            RuntimeError, match="No Google Earth Engine credentials available"
        ):
            runner.initialize_earth_engine()

    @patch("rollbar.report_message")
    def test_initialize_earth_engine_reports_to_rollbar(self, mock_rollbar_report):
        """Test that missing credentials are reported to Rollbar."""
        with pytest.raises(RuntimeError):
            runner.initialize_earth_engine()

        mock_rollbar_report.assert_called_once()
        call_kwargs = mock_rollbar_report.call_args
        assert call_kwargs[0][0] == "Missing GEE credentials"
        extra = call_kwargs[1]["extra_data"]
        # Core credential availability flags must be present
        assert extra["oauth_available"] is False
        assert extra["service_account_available"] is False
        # Rollbar context fields from _get_rollbar_extra_data()
        assert extra["source"] == "trends.earth-environment"
        assert extra["error_location"] == "initialize_earth_engine"

    @patch.dict(
        os.environ,
        {"GEE_OAUTH_ACCESS_TOKEN": "tok", "GEE_OAUTH_REFRESH_TOKEN": "ref"},
    )
    @patch("gefcore.runner._initialize_ee_with_oauth")
    def test_initialize_earth_engine_oauth_success(self, mock_oauth):
        """Test initialization succeeds via OAuth path."""
        mock_oauth.return_value = True
        # Should not raise
        runner.initialize_earth_engine()
        mock_oauth.assert_called_once()

    @patch.dict(
        os.environ,
        {"GEE_OAUTH_ACCESS_TOKEN": "tok", "GEE_OAUTH_REFRESH_TOKEN": "ref"},
    )
    @patch("gefcore.runner._initialize_ee_with_oauth")
    @patch("gefcore.runner._has_service_account_file")
    @patch("gefcore.runner._initialize_ee_with_service_account")
    def test_initialize_earth_engine_oauth_fallback(
        self, mock_sa_init, mock_has_sa, mock_oauth
    ):
        """Test fallback to service account when OAuth fails."""
        mock_oauth.return_value = False
        mock_has_sa.return_value = True
        mock_sa_init.return_value = True
        runner.initialize_earth_engine()
        mock_oauth.assert_called_once()
        mock_sa_init.assert_called_once()


class TestInitializeEEWithOAuth:
    """Test the _initialize_ee_with_oauth helper."""

    @patch.dict(
        os.environ,
        {
            "GEE_OAUTH_ACCESS_TOKEN": "access",
            "GEE_OAUTH_REFRESH_TOKEN": "refresh",
            "GOOGLE_OAUTH_CLIENT_ID": "cid",
            "GOOGLE_OAUTH_CLIENT_SECRET": "csecret",
        },
    )
    @patch("ee.Initialize")
    def test_oauth_success(self, mock_ee_init):
        """Test successful OAuth initialization."""
        result = runner._initialize_ee_with_oauth()
        assert result is True
        mock_ee_init.assert_called_once()

    @patch.dict(
        os.environ,
        {
            "GEE_OAUTH_ACCESS_TOKEN": "access",
            "GEE_OAUTH_REFRESH_TOKEN": "refresh",
        },
    )
    @patch("ee.Initialize", side_effect=Exception("ee error"))
    @patch("rollbar.report_exc_info")
    def test_oauth_ee_error(self, mock_rollbar, mock_ee_init):
        """Test OAuth initialization returns False on EE error."""
        result = runner._initialize_ee_with_oauth()
        assert result is False
        mock_rollbar.assert_called_once()


class TestInitializeEEWithServiceAccount:
    """Test the _initialize_ee_with_service_account helper."""

    @patch.dict(os.environ, {"EE_SERVICE_ACCOUNT_JSON": ""}, clear=False)
    @patch("gefcore.runner._has_service_account_file", return_value=False)
    def test_no_credentials_returns_false(self, mock_has_file):
        """Test returns False when no service account credentials available."""
        # Remove env var so it's falsy
        os.environ.pop("EE_SERVICE_ACCOUNT_JSON", None)
        result = runner._initialize_ee_with_service_account()
        assert result is False

    @patch.dict(
        os.environ,
        {"EE_SERVICE_ACCOUNT_JSON": ""},
        clear=False,
    )
    @patch("ee.Initialize", side_effect=Exception("sa error"))
    @patch("ee.ServiceAccountCredentials")
    @patch("rollbar.report_exc_info")
    @patch("gefcore.runner._has_service_account_file", return_value=False)
    def test_service_account_general_exception(
        self, mock_has_file, mock_rollbar, mock_sa_creds, mock_ee_init
    ):
        """Test outer except block reports to Rollbar."""
        import base64
        import json

        sa_json = json.dumps({"client_email": "test@test.iam.gserviceaccount.com"})
        os.environ["EE_SERVICE_ACCOUNT_JSON"] = base64.b64encode(
            sa_json.encode()
        ).decode()
        # Force the outer except by making ServiceAccountCredentials raise
        mock_sa_creds.side_effect = Exception("sa error")
        result = runner._initialize_ee_with_service_account()
        assert result is False
        mock_rollbar.assert_called_once()

    @patch.dict(
        os.environ,
        {"EE_SERVICE_ACCOUNT_JSON": "not-valid-base64!!!"},
        clear=False,
    )
    @patch("gefcore.runner._has_service_account_file", return_value=False)
    def test_bad_base64_returns_false(self, mock_has_file):
        """Test returns False when base64 decode fails."""
        result = runner._initialize_ee_with_service_account()
        assert result is False


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
        # Attach capture handler directly to runner.logger (propagate=False
        # means root-level capture_logs won't see messages).
        import logging

        handler = logging.StreamHandler(capture_logs)
        runner.logger.addHandler(handler)

        capture_logs.seek(0)
        capture_logs.truncate(0)

        runner.change_status_ticket("RUNNING")

        log_output = capture_logs.getvalue()
        assert "Changing to RUNNING" in log_output

        runner.logger.removeHandler(handler)

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
        import logging

        handler = logging.StreamHandler(capture_logs)
        runner.logger.addHandler(handler)

        capture_logs.seek(0)
        capture_logs.truncate(0)

        test_results = {"output": "test_data", "success": True}
        runner.send_result(test_results)

        log_output = capture_logs.getvalue()
        assert "Finished -> Results:" in log_output
        assert "test_data" in log_output

        runner.logger.removeHandler(handler)


class TestRunFunction:
    """Test the main run function."""

    @patch("ee.data.setDeadline")
    @patch("gefcore.runner.initialize_earth_engine")
    @patch("gefcore.runner.change_status_ticket")
    @patch("gefcore.runner.get_params")
    @patch("gefcore.runner.send_result")
    @patch("gefcore.runner.main")
    def test_run_success_flow(
        self,
        mock_main,
        mock_send_result,
        mock_get_params,
        mock_change_status,
        mock_init_ee,
        mock_set_deadline,
    ):
        """Test successful execution flow of run function."""
        mock_get_params.return_value = {"param1": "value1"}
        mock_main.run.return_value = {"result": "success"}

        runner.run()

        mock_init_ee.assert_called_once()
        mock_set_deadline.assert_called_once_with(120_000)
        mock_change_status.assert_called_with("RUNNING")
        mock_get_params.assert_called_once()

        expected_params = {
            "param1": "value1",
            "ENV": os.getenv("ENV"),
            "EXECUTION_ID": os.getenv("EXECUTION_ID"),
        }
        mock_main.run.assert_called_once_with(expected_params, runner.logger)
        mock_send_result.assert_called_once_with({"result": "success"})

    @patch("ee.data.setDeadline")
    @patch("gefcore.runner.initialize_earth_engine")
    @patch("gefcore.runner.change_status_ticket")
    @patch("rollbar.report_exc_info")
    def test_run_handles_earth_engine_initialization_error(
        self, mock_rollbar, mock_change_status, mock_init_ee, mock_set_deadline
    ):
        """Test run function handles Earth Engine initialization errors."""
        mock_init_ee.side_effect = Exception("EE initialization failed")

        with pytest.raises(Exception, match="EE initialization failed"):
            runner.run()

        mock_change_status.assert_called_with("FAILED")
        mock_rollbar.assert_called_once()

    @patch("ee.data.setDeadline")
    @patch("gefcore.runner.initialize_earth_engine")
    @patch("gefcore.runner.change_status_ticket")
    @patch("gefcore.runner.get_params")
    @patch("rollbar.report_exc_info")
    def test_run_handles_missing_main_module(
        self,
        mock_rollbar,
        mock_get_params,
        mock_change_status,
        mock_init_ee,
        mock_set_deadline,
    ):
        """Test run function handles missing main script module."""
        with patch.object(runner, "main", None):
            mock_get_params.return_value = {}

            with pytest.raises(
                ImportError, match="gefcore.script.main module not found"
            ):
                runner.run()

            mock_change_status.assert_called_with("FAILED")
            mock_rollbar.assert_called_once()

    @patch("ee.data.setDeadline")
    @patch("gefcore.runner.initialize_earth_engine")
    @patch("gefcore.runner.change_status_ticket")
    @patch("gefcore.runner.get_params")
    @patch("gefcore.runner.main")
    @patch("rollbar.report_exc_info")
    def test_run_handles_main_script_error(
        self,
        mock_rollbar,
        mock_main,
        mock_get_params,
        mock_change_status,
        mock_init_ee,
        mock_set_deadline,
    ):
        """Test run function handles errors in main script execution."""
        mock_get_params.return_value = {}
        mock_main.run.side_effect = Exception("Script execution failed")

        with pytest.raises(Exception, match="Script execution failed"):
            runner.run()

        mock_change_status.assert_called_with("FAILED")
        mock_rollbar.assert_called_once()

    @patch("ee.data.setDeadline")
    @patch("gefcore.runner.initialize_earth_engine")
    @patch("gefcore.runner.change_status_ticket")
    @patch("gefcore.runner.get_params")
    @patch("gefcore.runner.send_result")
    @patch("gefcore.runner.main")
    def test_run_passes_environment_variables_to_main(
        self,
        mock_main,
        mock_send_result,
        mock_get_params,
        mock_change_status,
        mock_init_ee,
        mock_set_deadline,
    ):
        """Test that run function passes environment variables to main script."""
        os.environ["EXECUTION_ID"] = "test_execution_123"
        os.environ["ENV"] = "test"

        mock_get_params.return_value = {"script_param": "value"}
        mock_main.run.return_value = {"result": "test"}

        runner.run()

        call_args = mock_main.run.call_args[0][0]
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
