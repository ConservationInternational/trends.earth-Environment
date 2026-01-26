"""API"""

import contextlib
import functools
import gzip
import json
import logging
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

import boto3
import requests
import rollbar
from tenacity import (
    RetryError,
    retry,
    retry_if_not_exception_type,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential,
)

# Configure logger for this module
logger = logging.getLogger(__name__)


class UUIDEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles UUID objects by converting them to strings."""

    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        return super().default(obj)


def validate_required_env_vars():
    """
    Validate that all required environment variables are set.

    Raises:
        ValueError: If any required environment variable is missing
    """
    required_vars = {
        "API_URL": "API base URL",
        "API_USER": "API username/email",
        "API_PASSWORD": "API password",
        "EXECUTION_ID": "Execution ID",
        "PARAMS_S3_PREFIX": "S3 parameters prefix",
        "PARAMS_S3_BUCKET": "S3 parameters bucket",
    }

    missing_vars = []
    for var_name, description in required_vars.items():
        if not os.getenv(var_name):
            missing_vars.append(f"{var_name} ({description})")

    if missing_vars:
        error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
        logger.error(error_msg)
        raise ValueError(error_msg)


def _create_error_details(response, request_payload=None):
    """
    Create standardized error details dictionary for API response errors.

    Args:
        response: requests.Response object
        request_payload: Optional request payload to include in error details

    Returns:
        dict: Standardized error details
    """
    # Sanitize sensitive headers
    safe_headers = {}
    sensitive_header_keys = {"authorization", "x-api-key", "cookie", "set-cookie"}

    for key, value in response.headers.items():
        if key.lower() in sensitive_header_keys:
            safe_headers[key] = "***REDACTED***"
        else:
            safe_headers[key] = value

    error_details = {
        "status_code": response.status_code,
        "response_text": response.text[:1000],  # Limit to avoid excessive data
        "response_headers": safe_headers,
        "request_url": response.request.url,
        "request_method": response.request.method,
        "execution_id": os.getenv("EXECUTION_ID"),
    }

    if request_payload is not None:
        # Sanitize sensitive data from payload
        sanitized_payload = request_payload
        if isinstance(request_payload, dict):
            sanitized_payload = request_payload.copy()
            sensitive_keys = {
                "password",
                "token",
                "secret",
                "key",
                "credential",
                "auth",
            }
            for key in list(sanitized_payload.keys()):
                if any(
                    sensitive_word in key.lower() for sensitive_word in sensitive_keys
                ):
                    sanitized_payload[key] = "***REDACTED***"

        # Convert payload to string to check size
        payload_str = (
            json.dumps(sanitized_payload, cls=UUIDEncoder)
            if isinstance(sanitized_payload, dict)
            else str(sanitized_payload)
        )

        # If payload is too large (>5KB), only include keys/structure info
        if len(payload_str) > 5000:
            if isinstance(sanitized_payload, dict):
                error_details["request_payload_keys"] = list(sanitized_payload.keys())
                error_details["request_payload_size"] = len(payload_str)
                error_details["request_payload_truncated"] = True
            else:
                error_details["request_payload_size"] = len(payload_str)
                error_details["request_payload_type"] = type(sanitized_payload).__name__
                error_details["request_payload_truncated"] = True
        else:
            error_details["request_payload"] = sanitized_payload

    # Try to get JSON response if possible
    with contextlib.suppress(ValueError, requests.exceptions.JSONDecodeError):
        error_details["response_json"] = response.json()

    return error_details


def _handle_api_error(
    response, operation_name, request_payload=None, raise_exception=True
):
    """
    Handle API error responses with standardized logging and error reporting.

    Args:
        response: requests.Response object
        operation_name: Name of the operation for logging (e.g., "logging in", "patching execution")
        request_payload: Optional request payload to include in error details
        raise_exception: Whether to raise an exception after logging

    Returns:
        None

    Raises:
        Exception: If raise_exception is True and response status is not 200
    """
    if response.status_code == 200:
        return

    error_details = _create_error_details(response, request_payload)

    error_msg = f"Error {operation_name} - Status: {response.status_code}, URL: {response.request.url}"
    logger.error(error_msg)
    logger.debug(f"{operation_name.title()} error details: {error_details}")

    # Always print API errors to stderr as backup when logging might fail
    # This ensures we can see error details even if the API logger is failing
    print(f"API Error Details: {error_msg}", file=sys.stderr)
    print(f"Response Text: {response.text[:500]}", file=sys.stderr)
    if error_details:
        print(f"Full Error Details: {error_details}", file=sys.stderr)

    # Report to Rollbar with full exception context if available, otherwise use message
    try:
        # Try to capture current exception context for full traceback
        rollbar.report_exc_info(extra_data=error_details)
    except Exception:
        # Fallback to message-only reporting if no exception context available
        rollbar.report_message(f"Error {operation_name}", extra_data=error_details)

    if raise_exception:
        raise Exception(
            f"Error {operation_name} - HTTP {response.status_code}: {response.text[:200]}"
        )


# Only validate environment variables if running in production or staging
ENV = os.getenv("ENV")
if ENV in ("prod", "production", "staging"):
    validate_required_env_vars()


API_URL = os.getenv("API_URL")
EMAIL = os.getenv("API_USER")
PASSWORD = os.getenv("API_PASSWORD")
EXECUTION_ID = os.getenv("EXECUTION_ID")
PARAMS_S3_PREFIX = os.getenv("PARAMS_S3_PREFIX")
PARAMS_S3_BUCKET = os.getenv("PARAMS_S3_BUCKET")


def _require_var(var, name):
    if var is None or var == "":
        env = os.getenv("ENV")
        if env not in ("prod", "production", "staging"):
            raise RuntimeError(
                f"Environment variable '{name}' is required for this operation.\n"
                f"You are running in ENV={env!r}. This is expected for local development, "
                f"but this function cannot be used without '{name}'."
            )
        else:
            raise RuntimeError(f"Missing required environment variable: {name}")
    return var


# Default timeout for HTTP requests (in seconds)
DEFAULT_REQUEST_TIMEOUT = 30

# Token storage - store both access and refresh tokens with expiration tracking
_access_token = None
_refresh_token = None
_token_expires_at = None

# Circuit breaker for authentication failures
_auth_failure_count = 0
_auth_circuit_breaker_until = None
_max_auth_failures = 5
_circuit_breaker_duration = 300  # 5 minutes
_last_circuit_breaker_rollbar_report = None
_circuit_breaker_rollbar_cooldown = 120  # Only report to rollbar once every 2 minutes

# Rate limiting for rollbar reports in retry logic
_retry_rollbar_reports = {}  # {function_name: {"last_report": timestamp, "count": count}}
_retry_rollbar_cooldown = 300  # 5 minutes between retry rollbar reports per function
_max_retry_rollbar_reports = 5  # Max reports per function per cooldown period


def _should_report_retry_to_rollbar(func_name):
    """
    Check if we should report a retry failure to rollbar based on rate limiting.

    Args:
        func_name (str): Name of the function being retried

    Returns:
        bool: True if we should report to rollbar, False if rate limited
    """
    global _retry_rollbar_reports

    current_time = time.time()

    if func_name not in _retry_rollbar_reports:
        _retry_rollbar_reports[func_name] = {"last_report": 0, "count": 0}

    report_data = _retry_rollbar_reports[func_name]

    # Reset count if cooldown period has passed
    if current_time - report_data["last_report"] > _retry_rollbar_cooldown:
        report_data["count"] = 0

    # Check if we've exceeded the max reports for this period
    if report_data["count"] >= _max_retry_rollbar_reports:
        return False

    # Update the tracking data
    report_data["last_report"] = current_time
    report_data["count"] += 1

    return True


class AuthenticationError(Exception):
    """Exception raised for authentication failures that should not be retried."""

    pass


def _is_auth_error(exception):
    """Check if exception is an authentication error (401 or 403)."""
    error_str = str(exception)
    return "401" in error_str or "403" in error_str


def _log_retry_attempt(retry_state):
    """Log retry attempt with details for debugging."""
    func_name = retry_state.fn.__name__
    attempt = retry_state.attempt_number
    exception = retry_state.outcome.exception()

    logger.warning(f"API call to {func_name} failed (attempt {attempt}), retrying...")

    # Print detailed error info to stderr for debugging
    print(f"Retry {attempt} for {func_name}: {exception}", file=sys.stderr)

    # If it's a requests exception, try to get more details
    if hasattr(exception, "response"):
        response = exception.response
        if hasattr(response, "status_code"):
            print(
                f"HTTP {response.status_code}: {response.text[:500]}",
                file=sys.stderr,
            )
    elif hasattr(exception, "__class__"):
        print(f"Exception type: {exception.__class__.__name__}", file=sys.stderr)

    # Report to rollbar occasionally to avoid spam
    if (attempt <= 3 or attempt % 5 == 0) and _should_report_retry_to_rollbar(
        func_name
    ):
        rollbar.report_message(
            f"API call retry for {func_name}",
            extra_data={
                "attempt": attempt,
                "error": str(exception),
            },
        )


def _report_retry_exhausted(retry_state):
    """Report to rollbar when retries are exhausted."""
    func_name = retry_state.fn.__name__
    attempt = retry_state.attempt_number
    exception = retry_state.outcome.exception()

    if _should_report_retry_to_rollbar(func_name):
        rollbar.report_message(
            f"Max retries exhausted for {func_name}",
            extra_data={
                "attempt": attempt,
                "error": str(exception),
            },
        )


def retry_api_call(max_duration_minutes=30, max_attempts=None):
    """
    Decorator to retry API calls with exponential backoff using tenacity.

    This decorator provides robust retry functionality with:
    - Exponential backoff starting at 1 second, capped at 120 seconds
    - Configurable maximum duration and attempt limits
    - Automatic logging of retry attempts
    - Integration with Rollbar for error reporting
    - Authentication error detection (no retry on 401/403)

    Args:
        max_duration_minutes (int): Maximum time to retry in minutes (default: 30)
        max_attempts (int): Maximum number of retry attempts (default: None for no limit)

    Returns:
        Decorated function that will retry on failure

    Example:
        @retry_api_call(max_duration_minutes=5, max_attempts=3)
        def my_api_function():
            # API call that may fail
            pass
    """
    max_duration_seconds = max_duration_minutes * 60

    # Build stop condition: combine time limit and optional attempt limit
    if max_attempts:
        stop_condition = stop_after_delay(max_duration_seconds) | stop_after_attempt(
            max_attempts
        )
    else:
        stop_condition = stop_after_delay(max_duration_seconds)

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Create the retry decorator with tenacity
            retry_decorator = retry(
                # Exponential backoff: 1s, 2s, 4s, ... up to 120s max
                wait=wait_exponential(multiplier=1, min=1, max=120),
                stop=stop_condition,
                # Retry on any exception except AuthenticationError
                retry=retry_if_not_exception_type(AuthenticationError),
                # Log before each retry sleep
                before_sleep=_log_retry_attempt,
                # Don't reraise RetryError, let the original exception through
                reraise=True,
            )

            # Wrap the function to check for auth errors
            @retry_decorator
            def inner_call():
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    # Convert auth errors to non-retryable exceptions for login function
                    if func.__name__ == "login" and _is_auth_error(e):
                        logger.error(
                            f"Authentication failed for {func.__name__} - not retrying"
                        )
                        if _should_report_retry_to_rollbar(func.__name__):
                            rollbar.report_message(
                                f"Authentication error - not retrying {func.__name__}",
                                extra_data={"error": str(e)},
                            )
                        raise AuthenticationError(str(e)) from e
                    raise

            try:
                return inner_call()
            except RetryError as retry_error:
                # Report exhaustion to rollbar
                _report_retry_exhausted(retry_error.last_attempt)
                # Re-raise the original exception
                raise retry_error.last_attempt.exception() from retry_error

        return wrapper

    return decorator


@retry_api_call(max_duration_minutes=3, max_attempts=5)
def login():
    _require_var(API_URL, "API_URL")
    _require_var(EMAIL, "API_USER")
    _require_var(PASSWORD, "API_PASSWORD")
    """
    Authenticate with the API and store both access and refresh tokens.

    Returns:
        str: The access token for immediate use
    """
    global _access_token, _refresh_token, _token_expires_at
    global \
        _auth_failure_count, \
        _auth_circuit_breaker_until, \
        _last_circuit_breaker_rollbar_report

    # Check circuit breaker
    if _auth_circuit_breaker_until and time.time() < _auth_circuit_breaker_until:
        remaining = int(_auth_circuit_breaker_until - time.time())
        error_msg = (
            f"Authentication circuit breaker active for {remaining} more seconds"
        )
        logger.error(error_msg)

        # Only report to Rollbar if we haven't reported recently (prevent spam)
        current_time = time.time()
        if (
            _last_circuit_breaker_rollbar_report is None
            or current_time - _last_circuit_breaker_rollbar_report
            >= _circuit_breaker_rollbar_cooldown
        ):
            rollbar.report_message(
                "Authentication circuit breaker active",
                extra_data={"remaining_seconds": remaining},
            )
            _last_circuit_breaker_rollbar_report = current_time

        raise Exception(error_msg)

    try:
        response = requests.post(
            API_URL + "/auth",
            json={"email": EMAIL, "password": PASSWORD},
            timeout=DEFAULT_REQUEST_TIMEOUT,
        )

        _handle_api_error(response, "logging in")

        response_data = response.json()

        # Store both tokens based on the API response structure
        _access_token = response_data["access_token"]
        _refresh_token = response_data.get("refresh_token")

        # Calculate expiration time (subtract 60 seconds as buffer to refresh before expiry)
        expires_in = response_data.get(
            "expires_in", 3600
        )  # Default to 1 hour if not specified
        _token_expires_at = time.time() + expires_in - 60

        # Reset circuit breaker on successful login
        _auth_failure_count = 0
        _auth_circuit_breaker_until = None

        if _refresh_token:
            logger.debug(
                f"Successfully stored access and refresh tokens, expires in {expires_in} seconds"
            )
        else:
            logger.warning(
                "No refresh token found in login response - will fallback to full login for each request"
            )

        return _access_token

    except Exception as e:
        # Increment failure count and activate circuit breaker if needed
        _auth_failure_count += 1

        if _auth_failure_count >= _max_auth_failures:
            _auth_circuit_breaker_until = time.time() + _circuit_breaker_duration
            logger.error(
                f"Authentication circuit breaker activated after {_auth_failure_count} failures"
            )
            rollbar.report_message(
                "Authentication circuit breaker activated",
                extra_data={
                    "failure_count": _auth_failure_count,
                    "circuit_breaker_duration": _circuit_breaker_duration,
                },
            )

        raise e


@retry_api_call(max_duration_minutes=2, max_attempts=3)
def refresh_access_token():
    _require_var(API_URL, "API_URL")
    """
    Use the refresh token to get a new access token.

    Returns:
        str: New access token, or None if refresh failed
    """
    global _access_token, _refresh_token, _token_expires_at

    if not _refresh_token:
        logger.debug("No refresh token available - cannot refresh")
        return None

    try:
        # Use the refresh token to get a new access token
        response = requests.post(
            API_URL + "/auth/refresh",
            json={"refresh_token": _refresh_token},
            timeout=DEFAULT_REQUEST_TIMEOUT,
        )

        if response.status_code == 200:
            response_data = response.json()
            _access_token = response_data["access_token"]

            # Calculate new expiration time (subtract 60 seconds as buffer)
            expires_in = response_data.get(
                "expires_in", 3600
            )  # Default to 1 hour if not specified
            _token_expires_at = time.time() + expires_in - 60

            # Note: refresh token is reused (not rotated) based on the API response structure
            logger.debug(
                f"Successfully refreshed access token, expires in {expires_in} seconds"
            )
            return _access_token
        else:
            # Refresh failed - clear stored tokens and fallback to login
            logger.warning(
                f"Token refresh failed with status {response.status_code}: {response.text[:200]}"
            )
            _access_token = None
            _refresh_token = None
            _token_expires_at = None
            return None

    except Exception as e:
        logger.warning(f"Token refresh failed with exception: {str(e)}")
        _access_token = None
        _refresh_token = None
        _token_expires_at = None
        return None


def get_token_status():
    """
    Get the current status of stored tokens for debugging purposes.

    Returns:
        dict: Token status information
    """
    global _access_token, _refresh_token, _token_expires_at

    status = {
        "has_access_token": _access_token is not None,
        "has_refresh_token": _refresh_token is not None,
        "token_expires_at": _token_expires_at,
        "is_expired": is_token_expired() if _token_expires_at else None,
    }

    if _token_expires_at:
        time_until_expiry = _token_expires_at - time.time()
        status["seconds_until_expiry"] = max(0, int(time_until_expiry))

    return status


def is_token_expired():
    """
    Check if the current access token is expired or about to expire.

    Returns:
        bool: True if token is expired or will expire soon
    """
    global _token_expires_at

    if _token_expires_at is None:
        return True

    # Consider token expired if it expires in the next 10 seconds
    return time.time() >= (_token_expires_at - 10)


def get_access_token():
    """
    Get a valid access token, using refresh token if available or logging in if needed.
    Only refreshes the token if it's expired or about to expire.

    Returns:
        str: Valid access token
    """
    global _access_token, _refresh_token, _token_expires_at

    # If we have a valid, non-expired access token, return it
    if _access_token and not is_token_expired():
        logger.debug("Using existing valid access token")
        return _access_token

    # If token is expired but we have a refresh token, try to refresh
    if _access_token and _refresh_token and is_token_expired():
        logger.debug("Access token expired, attempting refresh")
        refreshed_token = refresh_access_token()
        if refreshed_token:
            return refreshed_token

    # If refresh failed or we don't have tokens, perform full login
    logger.debug("Performing full login to get new tokens")
    return login()


def make_authenticated_request(method, url, **kwargs):
    _require_var(API_URL, "API_URL")
    """
    Make an authenticated API request with automatic token refresh on 401 errors.
    Automatically adds compression support for large payloads.

    Args:
        method (str): HTTP method (GET, POST, PATCH, etc.)
        url (str): Full URL for the request
        **kwargs: Additional arguments to pass to requests

    Returns:
        requests.Response: The response object
    """
    # Ensure we have an Authorization header
    if "headers" not in kwargs:
        kwargs["headers"] = {}

    # Set default timeout if not provided
    if "timeout" not in kwargs:
        kwargs["timeout"] = DEFAULT_REQUEST_TIMEOUT

    # Add compression support - request compressed responses from server
    kwargs["headers"]["Accept-Encoding"] = "gzip, deflate"

    # Add compression for outgoing requests if we have JSON data
    if "json" in kwargs and kwargs["json"]:
        try:
            # Always serialize JSON with UUID support first to check size and ensure compatibility
            json_str = json.dumps(
                kwargs["json"], separators=(",", ":"), cls=UUIDEncoder
            )

            # Check if the JSON payload is large enough to benefit from compression
            if len(json_str) > 1000:  # Only compress if >1KB
                # Compress the JSON data
                compressed_data = gzip.compress(json_str.encode("utf-8"))
                compression_ratio = len(json_str) / len(compressed_data)

                # Only use compression if it saves significant space (>20% reduction)
                if compression_ratio > 1.2:
                    logger.debug(
                        f"Compressing request payload: {len(json_str)} -> "
                        f"{len(compressed_data)} bytes "
                        f"(ratio: {compression_ratio:.2f}x)"
                    )
                    # Replace json with compressed data
                    kwargs["data"] = compressed_data
                    kwargs["headers"]["Content-Type"] = "application/json"
                    kwargs["headers"]["Content-Encoding"] = "gzip"
                    # Remove the json parameter since we're using data instead
                    del kwargs["json"]
                else:
                    # Compression not effective, but still need to handle UUIDs
                    # Convert the JSON data to ensure UUID compatibility
                    kwargs["json"] = json.loads(json_str)
            else:
                # Small payload, no compression, but still need to handle UUIDs
                # Convert the JSON data to ensure UUID compatibility
                kwargs["json"] = json.loads(json_str)
        except Exception as e:
            # If compression fails, fall back to uncompressed
            logger.debug(f"Request compression failed, using uncompressed: {e}")

    # First attempt with current token
    jwt = get_access_token()
    kwargs["headers"]["Authorization"] = f"Bearer {jwt}"

    response = requests.request(
        method,
        url,
        timeout=kwargs.get("timeout", DEFAULT_REQUEST_TIMEOUT),
        **{k: v for k, v in kwargs.items() if k != "timeout"},
    )

    # If we get 401 (Unauthorized), try refreshing the token once
    if response.status_code == 401:
        logger.debug("Received 401 error, attempting token refresh")

        # Clear current tokens and get fresh ones
        global _access_token, _refresh_token, _token_expires_at
        _access_token = None
        _refresh_token = None
        _token_expires_at = None

        # Try to get new token, but don't let this cause infinite retries
        try:
            jwt = get_access_token()
            kwargs["headers"]["Authorization"] = f"Bearer {jwt}"

            # Retry the request with new token
            response = requests.request(
                method,
                url,
                timeout=kwargs.get("timeout", DEFAULT_REQUEST_TIMEOUT),
                **{k: v for k, v in kwargs.items() if k != "timeout"},
            )
        except Exception as e:
            # If authentication completely fails, don't retry - return the original 401
            logger.error(f"Failed to refresh authentication after 401 error: {str(e)}")
            rollbar.report_message(
                "Authentication refresh failed after 401",
                extra_data={"original_url": url, "error": str(e)},
            )
            # Return the original 401 response instead of retrying indefinitely
            pass

    return response


@retry_api_call(max_duration_minutes=10)
def _get_params_from_s3(out_path):
    _require_var(PARAMS_S3_PREFIX, "PARAMS_S3_PREFIX")
    _require_var(EXECUTION_ID, "EXECUTION_ID")
    _require_var(PARAMS_S3_BUCKET, "PARAMS_S3_BUCKET")
    object_name = PARAMS_S3_PREFIX + "/" + EXECUTION_ID + ".json.gz"
    s3 = boto3.client("s3")
    s3.download_file(PARAMS_S3_BUCKET, object_name, str(out_path))


def get_params():
    with tempfile.TemporaryDirectory() as temp_dir:
        params_gz_file = Path(temp_dir) / (str(EXECUTION_ID) + ".json.gz")
        _get_params_from_s3(params_gz_file)
        with gzip.open(params_gz_file, "r") as fin:
            json_bytes = fin.read()
            json_str = json_bytes.decode("utf-8")
            params = json.loads(json_str)

    if params is None:
        error_msg = "Error getting parameters"
        logger.error(error_msg)
        rollbar.report_message("Error getting parameters")
        return None
    else:
        return params


@retry_api_call(max_duration_minutes=10)
def patch_execution(json):
    _require_var(API_URL, "API_URL")
    _require_var(EXECUTION_ID, "EXECUTION_ID")
    response = make_authenticated_request(
        "PATCH", API_URL + "/api/v1/execution/" + EXECUTION_ID, json=json
    )

    _handle_api_error(
        response, "patching execution", request_payload=json, raise_exception=False
    )


@retry_api_call(max_duration_minutes=10)
def save_log(json):
    _require_var(API_URL, "API_URL")
    _require_var(EXECUTION_ID, "EXECUTION_ID")
    response = make_authenticated_request(
        "POST", API_URL + "/api/v1/execution/" + EXECUTION_ID + "/log", json=json
    )

    _handle_api_error(
        response, "saving log", request_payload=json, raise_exception=False
    )
