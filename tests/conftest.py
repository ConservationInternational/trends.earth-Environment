"""Configuration and fixtures for pytest tests."""

import contextlib
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def setup_test_environment():
    """Setup test environment variables and state."""
    # Store original values
    original_env = {}
    test_env_vars = [
        "ENV",
        "TESTING",
        "EMAIL",
        "PASSWORD",
        "API_URL",
        "EXECUTION_ID",
        "PARAMS_S3_PREFIX",
        "PARAMS_S3_BUCKET",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_DEFAULT_REGION",
    ]

    for var in test_env_vars:
        original_env[var] = os.environ.get(var)

    # Set test values - provide default test values for all required vars
    os.environ.update(
        {
            "ENV": "test",
            "TESTING": "true",
            "EMAIL": "test@example.com",
            "PASSWORD": "testpass",
            "API_URL": "https://test-api.trendsearth.org",
            "EXECUTION_ID": "test-execution-123",
            "PARAMS_S3_PREFIX": "test-prefix",
            "PARAMS_S3_BUCKET": "test-bucket",
        }
    )

    yield

    # Restore original values
    for var, value in original_env.items():
        if value is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = value


@pytest.fixture
def reset_api_state():
    """Reset API module state between tests."""
    # Store original values
    from gefcore import api

    original_access_token = getattr(api, "_access_token", None)
    original_refresh_token = getattr(api, "_refresh_token", None)
    original_token_expires_at = getattr(api, "_token_expires_at", None)
    original_auth_failure_count = getattr(api, "_auth_failure_count", 0)
    original_circuit_breaker = getattr(api, "_auth_circuit_breaker_until", None)

    # Reset to clean state
    api._access_token = None
    api._refresh_token = None
    api._token_expires_at = None
    api._auth_failure_count = 0
    api._auth_circuit_breaker_until = None

    yield

    # Restore original values
    api._access_token = original_access_token
    api._refresh_token = original_refresh_token
    api._token_expires_at = original_token_expires_at
    api._auth_failure_count = original_auth_failure_count
    api._auth_circuit_breaker_until = original_circuit_breaker


@pytest.fixture
def mock_rollbar():
    """Mock rollbar to avoid external dependencies in tests."""
    with patch("rollbar.init") as mock_init, patch(
        "rollbar.report_exc_info"
    ) as mock_report_exc, patch("rollbar.report_message") as mock_report_msg:
        yield {
            "init": mock_init,
            "report_exc_info": mock_report_exc,
            "report_message": mock_report_msg,
        }


@pytest.fixture
def mock_earth_engine():
    """Mock Google Earth Engine to avoid authentication in tests."""
    with patch("ee.Initialize") as mock_init, patch(
        "ee.ServiceAccountCredentials"
    ) as mock_creds:
        yield {
            "initialize": mock_init,
            "credentials": mock_creds,
        }


@pytest.fixture
def mock_api_calls():
    """Mock all API calls to avoid external dependencies."""
    with patch("gefcore.api.make_authenticated_request") as mock_request, patch(
        "gefcore.api.login"
    ) as mock_login, patch("gefcore.api.get_params") as mock_get_params, patch(
        "gefcore.api.patch_execution"
    ) as mock_patch, patch("gefcore.api.save_log") as mock_save_log:
        # Set up default return values
        mock_request.return_value = MagicMock(
            status_code=200, json=lambda: {"success": True}
        )
        mock_login.return_value = "test_token"
        mock_get_params.return_value = {"test_param": "test_value"}

        yield {
            "request": mock_request,
            "login": mock_login,
            "get_params": mock_get_params,
            "patch_execution": mock_patch,
            "save_log": mock_save_log,
        }


@pytest.fixture
def temp_service_account():
    """Create a temporary service account file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        service_account_content = {
            "type": "service_account",
            "project_id": "test_project",
            "private_key_id": "test_key_id",
            "private_key": "-----BEGIN PRIVATE KEY-----\ntest_private_key\n-----END PRIVATE KEY-----\n",
            "client_email": "test@test_project.iam.gserviceaccount.com",
            "client_id": "test_client_id",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        import json

        json.dump(service_account_content, f)
        temp_path = f.name

    yield temp_path

    # Cleanup
    with contextlib.suppress(OSError):
        os.unlink(temp_path)


@pytest.fixture
def capture_logs():
    """Capture log outputs for testing."""
    import logging
    from io import StringIO

    log_capture = StringIO()
    handler = logging.StreamHandler(log_capture)

    # Get the root logger and add our handler
    logger = logging.getLogger()
    original_level = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)

    yield log_capture

    # Cleanup
    logger.removeHandler(handler)
    logger.setLevel(original_level)
