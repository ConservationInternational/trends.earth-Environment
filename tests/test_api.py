"""Comprehensive tests for the gefcore.api module."""

import gzip
import json
import os
import tempfile
import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from gefcore import api


class TestValidateRequiredEnvVars:
    """Test the validate_required_env_vars function."""

    @patch.dict(
        os.environ,
        {
            "API_URL": "https://api.example.com",
            "API_USER": "testuser",
            "API_PASSWORD": "testpass",
            "EXECUTION_ID": "exec123",
            "PARAMS_S3_PREFIX": "prefix",
            "PARAMS_S3_BUCKET": "bucket",
        },
        clear=False,
    )
    def test_validate_required_env_vars_success(self):
        """Test successful validation when all required vars are present."""
        # Should not raise any exception
        api.validate_required_env_vars()

    @patch.dict(os.environ, {}, clear=True)
    def test_validate_required_env_vars_missing_all(self):
        """Test validation fails when all required vars are missing."""
        with pytest.raises(ValueError, match="Missing required environment variables"):
            api.validate_required_env_vars()

    @patch.dict(
        os.environ,
        {
            "API_URL": "https://api.example.com",
            "API_USER": "",  # Empty string should be treated as missing
            "API_PASSWORD": "testpass",
            "EXECUTION_ID": "exec123",
            "PARAMS_S3_PREFIX": "prefix",
            "PARAMS_S3_BUCKET": "bucket",
        },
        clear=False,
    )
    def test_validate_required_env_vars_empty_string(self):
        """Test validation fails when a required var is empty string."""
        with pytest.raises(ValueError, match="Missing required environment variables"):
            api.validate_required_env_vars()


class TestCreateErrorDetails:
    """Test the _create_error_details function."""

    def test_create_error_details_basic(self):
        """Test basic error details creation."""
        # Create mock response
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.request.url = "https://api.example.com/test"
        mock_response.request.method = "GET"

        with patch.dict(os.environ, {"EXECUTION_ID": "test-exec-123"}):
            error_details = api._create_error_details(mock_response)

        assert error_details["status_code"] == 404
        assert error_details["response_text"] == "Not Found"
        assert error_details["response_headers"] == {"Content-Type": "application/json"}
        assert error_details["request_url"] == "https://api.example.com/test"
        assert error_details["request_method"] == "GET"
        assert error_details["execution_id"] == "test-exec-123"

    def test_create_error_details_with_sensitive_headers(self):
        """Test error details creation with sensitive headers redacted."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_response.headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer secret-token",
            "X-API-Key": "secret-key",
            "Cookie": "session=abc123",
        }
        mock_response.request.url = "https://api.example.com/secure"
        mock_response.request.method = "POST"

        error_details = api._create_error_details(mock_response)

        assert error_details["response_headers"]["Authorization"] == "***REDACTED***"
        assert error_details["response_headers"]["X-API-Key"] == "***REDACTED***"
        assert error_details["response_headers"]["Cookie"] == "***REDACTED***"
        assert error_details["response_headers"]["Content-Type"] == "application/json"

    def test_create_error_details_with_payload(self):
        """Test error details creation with request payload."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_response.headers = {}
        mock_response.request.url = "https://api.example.com/test"
        mock_response.request.method = "POST"

        payload = {
            "username": "testuser",
            "password": "secret123",
            "data": "normal_data",
        }

        error_details = api._create_error_details(mock_response, payload)

        # Check that password is redacted
        assert "password" in error_details["request_payload"]
        assert error_details["request_payload"]["password"] == "***REDACTED***"  # noqa: S105
        assert error_details["request_payload"]["username"] == "testuser"
        assert error_details["request_payload"]["data"] == "normal_data"

    def test_create_error_details_long_response_text(self):
        """Test error details creation with long response text (should be truncated)."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Error: " + "x" * 2000  # Long error message
        mock_response.headers = {}
        mock_response.request.url = "https://api.example.com/test"
        mock_response.request.method = "GET"

        error_details = api._create_error_details(mock_response)

        # Response text should be truncated to 1000 characters
        assert len(error_details["response_text"]) == 1000


class TestRequireVar:
    """Test the _require_var function."""

    def test_require_var_valid_value(self):
        """Test _require_var with valid value."""
        # Should not raise any exception
        api._require_var("valid_value", "TEST_VAR")

    def test_require_var_none_value(self):
        """Test _require_var with None value."""
        with pytest.raises(
            RuntimeError, match="Environment variable 'TEST_VAR' is required"
        ):
            api._require_var(None, "TEST_VAR")

    def test_require_var_empty_string(self):
        """Test _require_var with empty string."""
        with pytest.raises(
            RuntimeError, match="Environment variable 'TEST_VAR' is required"
        ):
            api._require_var("", "TEST_VAR")


class TestShouldReportRetryToRollbar:
    """Test the _should_report_retry_to_rollbar function."""

    def test_should_report_retry_to_rollbar_first_time(self):
        """Test first retry should be reported."""
        # Clear any previous state
        api._retry_rollbar_reports.clear()

        result = api._should_report_retry_to_rollbar("test_function")
        assert result is True

    def test_should_report_retry_to_rollbar_cooldown(self):
        """Test retry reporting respects cooldown period."""
        # Clear any previous state and set up time tracking
        api._retry_rollbar_reports.clear()

        # Mock time to ensure we can control the cooldown period
        with patch("gefcore.api.time.time") as mock_time:
            # First call at time 0
            mock_time.return_value = 0
            result1 = api._should_report_retry_to_rollbar("test_function")
            assert result1 is True

            # Second call at time 1 (within 300 second cooldown)
            # This should still be True since count is only 1 (max is 5)
            mock_time.return_value = 1
            result2 = api._should_report_retry_to_rollbar("test_function")
            assert result2 is True

            # Make enough calls to exceed max reports (5)
            for i in range(3):  # 3 more calls (total will be 5)
                mock_time.return_value = i + 2
                api._should_report_retry_to_rollbar("test_function")

            # Now the 6th call should return False (exceeded max)
            mock_time.return_value = 10
            result_max_exceeded = api._should_report_retry_to_rollbar("test_function")
            assert result_max_exceeded is False

            # After cooldown period (300+ seconds), should return True again
            mock_time.return_value = 350  # 350 seconds later
            result_after_cooldown = api._should_report_retry_to_rollbar("test_function")
            assert result_after_cooldown is True


class TestHandleApiError:
    """Test the _handle_api_error function."""

    def test_handle_api_error_success_status(self):
        """Test _handle_api_error with successful status code."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None

        # Should not raise any exception
        api._handle_api_error(mock_response, "test action")

    def test_handle_api_error_client_error(self):
        """Test _handle_api_error with client error."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_response.headers = {}
        mock_response.request.url = "https://api.example.com/test"
        mock_response.request.method = "POST"

        with pytest.raises(Exception, match="Error test action - HTTP 400"):
            api._handle_api_error(mock_response, "test action")

    @patch("rollbar.report_message")
    def test_handle_api_error_server_error_with_rollbar(self, mock_rollbar):
        """Test _handle_api_error with server error and rollbar reporting."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.headers = {}
        mock_response.request.url = "https://api.example.com/test"
        mock_response.request.method = "GET"

        with pytest.raises(Exception, match="Error test action - HTTP 500"):
            api._handle_api_error(mock_response, "test action")

        # Verify rollbar was called for server error
        mock_rollbar.assert_called_once()


class TestLogin:
    """Test the login function."""

    def setup_method(self):
        """Reset authentication state before each test."""
        api._access_token = None
        api._refresh_token = None
        api._token_expires_at = None
        api._auth_failure_count = 0
        api._auth_circuit_breaker_until = None
        api._last_circuit_breaker_rollbar_report = None

    @patch("requests.post")
    @patch.object(api, "API_URL", "https://api.example.com")
    @patch.object(api, "EMAIL", "testuser")
    @patch.object(api, "PASSWORD", "testpass")
    def test_login_success(self, mock_post):
        """Test successful login."""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_response

        result = api.login()

        # Verify request was made correctly
        mock_post.assert_called_once_with(
            "https://api.example.com/auth",
            json={"email": "testuser", "password": "testpass"},
            timeout=30,
        )

        # Verify tokens were stored
        assert result == "test_access_token"
        assert api._access_token == "test_access_token"  # noqa: S105
        assert api._refresh_token == "test_refresh_token"  # noqa: S105
        assert api._token_expires_at is not None

    @patch("requests.post")
    @patch.object(api, "API_URL", "https://api.example.com")
    @patch.object(api, "EMAIL", "testuser")
    @patch.object(api, "PASSWORD", "testpass")
    def test_login_without_refresh_token(self, mock_post):
        """Test login without refresh token in response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "access_token": "test_access_token",
            "expires_in": 3600,
            # No refresh_token
        }
        mock_post.return_value = mock_response

        result = api.login()

        assert result == "test_access_token"
        assert api._access_token == "test_access_token"  # noqa: S105
        assert api._refresh_token is None

    @patch("rollbar.report_message")
    @patch.object(api, "API_URL", "https://api.example.com")
    @patch.object(api, "EMAIL", "testuser")
    @patch.object(api, "PASSWORD", "testpass")
    @patch(
        "gefcore.api.retry_api_call", lambda **kwargs: lambda func: func
    )  # Disable retry decorator
    def test_login_circuit_breaker(self, mock_rollbar):
        """Test login with circuit breaker active."""
        # Set circuit breaker to be active for a long time to ensure it's detected
        api._auth_circuit_breaker_until = time.time() + 3600  # 1 hour from now

        with pytest.raises(Exception, match="Authentication circuit breaker active"):
            api.login()

    @patch("requests.post")
    @patch("rollbar.report_message")
    @patch.object(api, "API_URL", "https://api.example.com")
    @patch.object(api, "EMAIL", "testuser")
    @patch.object(api, "PASSWORD", "testpass")
    def test_login_failure_count_increment(self, mock_rollbar, mock_post):
        """Test login failure increments failure count."""
        # Reset circuit breaker and failure count
        api._auth_circuit_breaker_until = None
        api._auth_failure_count = 0

        # Mock failed response
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_response.headers = {}
        mock_response.request.url = "https://api.example.com/auth"
        mock_response.request.method = "POST"
        mock_post.return_value = mock_response

        with pytest.raises(Exception, match="Error logging in"):
            api.login()

        # Verify failure count was incremented
        assert api._auth_failure_count > 0


class TestRefreshAccessToken:
    """Test the refresh_access_token function."""

    def setup_method(self):
        """Reset authentication state before each test."""
        api._access_token = None
        api._refresh_token = None
        api._token_expires_at = None
        api._auth_failure_count = 0
        api._auth_circuit_breaker_until = None
        api._last_circuit_breaker_rollbar_report = None

    @patch("requests.post")
    @patch.object(api, "API_URL", "https://api.example.com")
    def test_refresh_access_token_success(self, mock_post):
        """Test successful token refresh."""
        # Set up existing refresh token
        api._refresh_token = "test_refresh_token"  # noqa: S105

        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_access_token",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_response

        result = api.refresh_access_token()

        # Verify request was made correctly
        mock_post.assert_called_once_with(
            "https://api.example.com/auth/refresh",
            json={"refresh_token": "test_refresh_token"},
            timeout=30,
        )

        # Verify new token was stored
        assert result == "new_access_token"
        assert api._access_token == "new_access_token"  # noqa: S105

    @patch.object(api, "API_URL", "https://api.example.com")
    def test_refresh_access_token_no_refresh_token(self):
        """Test refresh when no refresh token is available."""
        api._refresh_token = None

        result = api.refresh_access_token()

        assert result is None

    @patch("requests.post")
    @patch.object(api, "API_URL", "https://api.example.com")
    def test_refresh_access_token_failure(self, mock_post):
        """Test token refresh failure."""
        api._refresh_token = "test_refresh_token"  # noqa: S105

        # Mock failed response
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Refresh token expired"
        mock_post.return_value = mock_response

        result = api.refresh_access_token()

        # Verify tokens were cleared
        assert result is None
        assert api._access_token is None
        assert api._refresh_token is None
        assert api._token_expires_at is None

    @patch("requests.post")
    @patch.object(api, "API_URL", "https://api.example.com")
    def test_refresh_access_token_exception(self, mock_post):
        """Test token refresh with exception."""
        api._refresh_token = "test_refresh_token"  # noqa: S105

        # Mock exception
        mock_post.side_effect = requests.exceptions.RequestException("Connection error")

        result = api.refresh_access_token()

        # Verify tokens were cleared
        assert result is None
        assert api._access_token is None
        assert api._refresh_token is None
        assert api._token_expires_at is None


class TestGetAccessToken:
    """Test the get_access_token function."""

    def setup_method(self):
        """Reset authentication state before each test."""
        api._access_token = None
        api._refresh_token = None
        api._token_expires_at = None
        api._auth_failure_count = 0
        api._auth_circuit_breaker_until = None
        api._last_circuit_breaker_rollbar_report = None

    @patch("gefcore.api.login")
    def test_get_access_token_no_token(self, mock_login):
        """Test get_access_token when no token exists."""
        mock_login.return_value = "new_token"

        result = api.get_access_token()

        mock_login.assert_called_once()
        assert result == "new_token"

    @patch("gefcore.api.is_token_expired")
    def test_get_access_token_valid_token(self, mock_is_expired):
        """Test get_access_token with valid existing token."""
        api._access_token = "existing_token"  # noqa: S105
        mock_is_expired.return_value = False

        result = api.get_access_token()

        assert result == "existing_token"

    @patch("gefcore.api.is_token_expired")
    @patch("gefcore.api.refresh_access_token")
    def test_get_access_token_expired_token_refresh_success(
        self, mock_refresh, mock_is_expired
    ):
        """Test get_access_token with expired token and successful refresh."""
        api._access_token = "expired_token"  # noqa: S105
        api._refresh_token = (
            "refresh_token"  # Need refresh token for refresh logic  # noqa: S105
        )
        mock_is_expired.return_value = True
        mock_refresh.return_value = "refreshed_token"

        result = api.get_access_token()

        mock_refresh.assert_called_once()
        assert result == "refreshed_token"

    @patch("gefcore.api.is_token_expired")
    @patch("gefcore.api.refresh_access_token")
    @patch("gefcore.api.login")
    def test_get_access_token_expired_token_refresh_failure(
        self, mock_login, mock_refresh, mock_is_expired
    ):
        """Test get_access_token with expired token and failed refresh."""
        api._access_token = "expired_token"  # noqa: S105
        api._refresh_token = (
            "refresh_token"  # Need refresh token for refresh logic  # noqa: S105
        )
        mock_is_expired.return_value = True
        mock_refresh.return_value = None  # Refresh failed
        mock_login.return_value = "new_login_token"

        result = api.get_access_token()

        mock_refresh.assert_called_once()
        mock_login.assert_called_once()
        assert result == "new_login_token"


class TestGetParamsFromS3:
    """Test the _get_params_from_s3 function."""

    @patch("boto3.client")
    @patch.object(api, "PARAMS_S3_BUCKET", "test-bucket")
    @patch.object(api, "PARAMS_S3_PREFIX", "test-prefix")
    @patch.object(api, "EXECUTION_ID", "test-exec-123")
    def test_get_params_from_s3_success(self, mock_boto_client):
        """Test successful parameter retrieval from S3."""
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        # Mock S3 download_file method
        def mock_download_file_gzip(bucket, key, local_path):
            # Create a gzipped JSON file at the target path
            test_params = {"param1": "value1", "param2": "value2"}
            gzipped_data = gzip.compress(json.dumps(test_params).encode())
            with open(local_path, "wb") as f:
                f.write(gzipped_data)

        mock_s3.download_file.side_effect = mock_download_file_gzip

        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = os.path.join(temp_dir, "params.json.gz")
            api._get_params_from_s3(out_path)

            # Verify file was created and contains correct data
            assert os.path.exists(out_path)
            with gzip.open(out_path, "r") as f:
                json_str = f.read().decode("utf-8")
                loaded_params = json.loads(json_str)
            assert loaded_params == {"param1": "value1", "param2": "value2"}

            # Verify S3 was called with correct parameters
            mock_s3.download_file.assert_called_once_with(
                "test-bucket", "test-prefix/test-exec-123.json.gz", out_path
            )

    @patch("boto3.client")
    @patch.object(api, "PARAMS_S3_BUCKET", "test-bucket")
    @patch.object(api, "PARAMS_S3_PREFIX", "test-prefix")
    @patch.object(api, "EXECUTION_ID", "test-exec-123")
    def test_get_params_from_s3_no_gzip(self, mock_boto_client):
        """Test parameter retrieval from S3 when file is not gzipped."""
        # This test doesn't make sense for the actual implementation since
        # _get_params_from_s3 always expects gzipped files, but we'll keep it simple
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        def mock_download_file_plain(bucket, key, local_path):
            # Create a plain JSON file (not gzipped, just for test)
            test_params = {"param1": "value1"}
            with open(local_path, "w") as f:
                json.dump(test_params, f)

        mock_s3.download_file.side_effect = mock_download_file_plain

        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = os.path.join(temp_dir, "params.json.gz")
            api._get_params_from_s3(out_path)

            # Verify file was created
            assert os.path.exists(out_path)


class TestGetParams:
    """Test the get_params function."""

    @patch("gefcore.api._get_params_from_s3")
    @patch.object(api, "EXECUTION_ID", "test-exec-123")
    def test_get_params_success(self, mock_get_from_s3):
        """Test successful parameter retrieval."""
        # Create a temporary file with test parameters (gzipped as expected)
        test_params = {"param1": "value1", "param2": "value2"}

        def mock_s3_download(out_path):
            # Create gzipped JSON file as the real function expects
            gzipped_data = gzip.compress(json.dumps(test_params).encode())
            with open(out_path, "wb") as f:
                f.write(gzipped_data)

        mock_get_from_s3.side_effect = mock_s3_download

        result = api.get_params()
        assert result == test_params
        mock_get_from_s3.assert_called_once()

    @patch("gefcore.api._get_params_from_s3")
    @patch.object(api, "EXECUTION_ID", "test-exec-123")
    def test_get_params_file_not_found(self, mock_get_from_s3):
        """Test parameter retrieval when file doesn't exist."""
        # Mock S3 download to raise FileNotFoundError
        mock_get_from_s3.side_effect = FileNotFoundError("File not found")

        with pytest.raises(FileNotFoundError):
            api.get_params()


class TestTokenFunctions:
    """Test token-related functions."""

    def test_is_token_expired_no_expiry(self):
        """Test is_token_expired when no expiry time is set."""
        # Clear token expiry
        api._token_expires_at = None

        result = api.is_token_expired()
        assert result is True

    def test_is_token_expired_not_expired(self):
        """Test is_token_expired when token is not expired."""
        import time

        # Set expiry time to future
        api._token_expires_at = time.time() + 3600  # 1 hour from now

        result = api.is_token_expired()
        assert result is False

    def test_is_token_expired_expired(self):
        """Test is_token_expired when token is expired."""
        import time

        # Set expiry time to past
        api._token_expires_at = time.time() - 3600  # 1 hour ago

        result = api.is_token_expired()
        assert result is True

    def test_get_token_status(self):
        """Test get_token_status function."""
        import time

        # Set up token state
        api._access_token = "test_token"  # noqa: S105
        api._refresh_token = "refresh_token"  # noqa: S105
        api._token_expires_at = time.time() + 3600

        status = api.get_token_status()

        assert status["has_access_token"] is True
        assert status["has_refresh_token"] is True
        assert status["is_expired"] is False
        assert "token_expires_at" in status
        assert "seconds_until_expiry" in status


class TestMakeAuthenticatedRequest:
    """Test the make_authenticated_request function."""

    @patch("gefcore.api.get_access_token")
    @patch("requests.request")
    @patch.object(api, "API_URL", "https://api.example.com")
    def test_make_authenticated_request_success(self, mock_request, mock_get_token):
        """Test successful authenticated request."""
        # Mock token retrieval
        mock_get_token.return_value = "test_access_token"

        # Mock successful HTTP response
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        result = api.make_authenticated_request("GET", "https://api.example.com/test")

        # Verify token was retrieved
        mock_get_token.assert_called_once()

        # Verify request was made with authorization header
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[0] == ("GET", "https://api.example.com/test")
        assert call_args[1]["headers"]["Authorization"] == "Bearer test_access_token"

        assert result == mock_response

    @patch("gefcore.api.get_access_token")
    @patch("requests.request")
    @patch.object(api, "API_URL", "https://api.example.com")
    def test_make_authenticated_request_with_existing_headers(
        self, mock_request, mock_get_token
    ):
        """Test authenticated request with existing headers."""
        mock_get_token.return_value = "test_access_token"
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        existing_headers = {"Content-Type": "application/json", "X-Custom": "value"}

        api.make_authenticated_request(
            "POST",
            "https://api.example.com/test",
            headers=existing_headers,
            json={"data": "test"},
        )

        # Verify headers were merged correctly
        call_args = mock_request.call_args
        headers = call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer test_access_token"
        assert headers["Content-Type"] == "application/json"
        assert headers["X-Custom"] == "value"


class TestPatchExecution:
    """Test the patch_execution function."""

    @patch("gefcore.api.make_authenticated_request")
    @patch.object(api, "API_URL", "https://api.example.com")
    @patch.object(api, "EXECUTION_ID", "test-exec-123")
    def test_patch_execution_success(self, mock_make_request):
        """Test successful execution patch."""
        mock_response = MagicMock()
        mock_make_request.return_value = mock_response

        test_data = {"status": "RUNNING", "progress": 50}

        api.patch_execution(json=test_data)

        # Verify request was made correctly
        mock_make_request.assert_called_once_with(
            "PATCH",
            "https://api.example.com/api/v1/execution/test-exec-123",
            json=test_data,
        )


class TestSaveLog:
    """Test the save_log function."""

    @patch("gefcore.api.make_authenticated_request")
    @patch.object(api, "API_URL", "https://api.example.com")
    @patch.object(api, "EXECUTION_ID", "test-exec-123")
    def test_save_log_success(self, mock_make_request):
        """Test successful log saving."""
        mock_response = MagicMock()
        mock_make_request.return_value = mock_response

        test_log = {"level": "INFO", "message": "Test log message"}

        api.save_log(json=test_log)

        # Verify request was made correctly
        mock_make_request.assert_called_once_with(
            "POST",
            "https://api.example.com/api/v1/execution/test-exec-123/log",
            json=test_log,
        )


class TestRetryDecorator:
    """Test the retry_api_call decorator."""

    def test_retry_decorator_success_first_attempt(self):
        """Test retry decorator when function succeeds on first attempt."""

        @api.retry_api_call(max_attempts=3)
        def test_function_first():
            return "success"

        result = test_function_first()
        assert result == "success"

    def test_retry_decorator_success_after_retry(self):
        """Test retry decorator when function succeeds after retries."""
        call_count = 0

        @api.retry_api_call(max_attempts=3)
        def test_function_retry():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise requests.exceptions.RequestException("Temporary error")
            return "success"

        result = test_function_retry()
        assert result == "success"
        assert call_count == 2

    def test_retry_decorator_max_attempts_exceeded(self):
        """Test retry decorator when max attempts are exceeded."""

        @api.retry_api_call(max_attempts=2)
        def test_function_fail():
            raise requests.exceptions.RequestException("Persistent error")

        with pytest.raises(requests.exceptions.RequestException):
            test_function_fail()
