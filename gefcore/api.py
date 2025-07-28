"""API"""

import functools
import gzip
import json
import logging
import os
import tempfile
import time
from pathlib import Path

import boto3
import requests
import rollbar

rollbar.init(os.getenv("ROLLBAR_SCRIPT_TOKEN"), os.getenv("ENV"))

# Configure logger for this module
logger = logging.getLogger(__name__)


def _create_error_details(response, request_payload=None):
    """
    Create standardized error details dictionary for API response errors.

    Args:
        response: requests.Response object
        request_payload: Optional request payload to include in error details

    Returns:
        dict: Standardized error details
    """
    error_details = {
        "status_code": response.status_code,
        "response_text": response.text[:1000],  # Limit to avoid excessive data
        "response_headers": dict(response.headers),
        "request_url": response.request.url,
        "request_method": response.request.method,
        "execution_id": EXECUTION_ID,
    }

    if request_payload is not None:
        # Convert payload to string to check size
        payload_str = (
            json.dumps(request_payload)
            if isinstance(request_payload, dict)
            else str(request_payload)
        )

        # If payload is too large (>5KB), only include keys/structure info
        if len(payload_str) > 5000:
            if isinstance(request_payload, dict):
                error_details["request_payload_keys"] = list(request_payload.keys())
                error_details["request_payload_size"] = len(payload_str)
                error_details["request_payload_truncated"] = True
            else:
                error_details["request_payload_size"] = len(payload_str)
                error_details["request_payload_type"] = type(request_payload).__name__
                error_details["request_payload_truncated"] = True
        else:
            error_details["request_payload"] = request_payload

    # Try to get JSON response if possible
    try:
        error_details["response_json"] = response.json()
    except (ValueError, requests.exceptions.JSONDecodeError):
        pass

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

    rollbar.report_message(f"Error {operation_name}", extra_data=error_details)

    if raise_exception:
        raise Exception(
            f"Error {operation_name} - HTTP {response.status_code}: {response.text[:200]}"
        )


API_URL = os.getenv("API_URL", None)
EMAIL = os.getenv("API_USER", None)
PASSWORD = os.getenv("API_PASSWORD", None)
EXECUTION_ID = os.getenv("EXECUTION_ID", None)
PARAMS_S3_PREFIX = os.getenv("PARAMS_S3_PREFIX", None)
PARAMS_S3_BUCKET = os.getenv("PARAMS_S3_BUCKET", None)


def retry_api_call(max_duration_minutes=30):
    """
    Decorator to retry API calls with exponential backoff for up to max_duration_minutes.

    Args:
        max_duration_minutes (int): Maximum time to retry in minutes (default: 30)

    Returns:
        Decorated function that will retry on failure
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            max_duration_seconds = max_duration_minutes * 60
            start_time = time.time()
            attempt = 0
            base_delay = 1  # Start with 1 second delay

            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempt += 1
                    elapsed_time = time.time() - start_time

                    # Calculate delay with exponential backoff (capped at 120 seconds)
                    delay = min(base_delay * (2 ** (attempt - 1)), 120)

                    # Check if we would exceed the time limit with the next delay
                    if elapsed_time + delay > max_duration_seconds:
                        error_msg = f"Max retry duration of {max_duration_minutes} minutes exceeded"
                        logger.error(error_msg)
                        rollbar.report_message(
                            f"Max retry duration exceeded for {func.__name__}",
                            extra_data={
                                "attempt": attempt,
                                "elapsed_time": elapsed_time,
                            },
                        )
                        raise e

                    retry_msg = f"API call failed (attempt {attempt}), retrying in {delay} seconds..."
                    logger.warning(retry_msg)
                    rollbar.report_message(
                        f"API call retry for {func.__name__}",
                        extra_data={
                            "attempt": attempt,
                            "delay": delay,
                            "error": str(e),
                        },
                    )

                    time.sleep(delay)

        return wrapper

    return decorator


@retry_api_call(max_duration_minutes=10)
def login():
    response = requests.post(
        API_URL + "/auth", json={"email": EMAIL, "password": PASSWORD}
    )

    _handle_api_error(response, "logging in")
    return response.json()["access_token"]


@retry_api_call(max_duration_minutes=10)
def _get_params_from_s3(out_path):
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
    jwt = login()
    response = requests.patch(
        API_URL + "/api/v1/execution/" + EXECUTION_ID,
        json=json,
        headers={"Authorization": "Bearer " + jwt},
    )

    _handle_api_error(
        response, "patching execution", request_payload=json, raise_exception=False
    )


@retry_api_call(max_duration_minutes=10)
def save_log(json):
    jwt = login()
    response = requests.post(
        API_URL + "/api/v1/execution/" + EXECUTION_ID + "/log",
        json=json,
        headers={"Authorization": "Bearer " + jwt},
    )

    _handle_api_error(
        response, "saving log", request_payload=json, raise_exception=False
    )
