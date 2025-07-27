"""API"""

import os
import tempfile
import json
import gzip
import time
import functools
from pathlib import Path

import rollbar
import boto3
import requests

rollbar.init(os.getenv("ROLLBAR_SCRIPT_TOKEN"), os.getenv("ENV"))

API_URL = os.getenv("API_URL", None)
EMAIL = os.getenv("API_USER", None)
PASSWORD = os.getenv("API_PASSWORD", None)
EXECUTION_ID = os.getenv("EXECUTION_ID", None)
PARAMS_S3_PREFIX = os.getenv("PARAMS_S3_PREFIX", None)
PARAMS_S3_BUCKET = os.getenv("PARAMS_S3_BUCKET", None)


def retry_api_call(max_duration_minutes=10):
    """
    Decorator to retry API calls with exponential backoff for up to max_duration_minutes.

    Args:
        max_duration_minutes (int): Maximum time to retry in minutes (default: 10)

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

                    # Calculate delay with exponential backoff (capped at 60 seconds)
                    delay = min(base_delay * (2 ** (attempt - 1)), 60)

                    # Check if we would exceed the time limit with the next delay
                    if elapsed_time + delay > max_duration_seconds:
                        print(
                            f"Max retry duration of {max_duration_minutes} minutes exceeded"
                        )
                        rollbar.report_message(
                            f"Max retry duration exceeded for {func.__name__}",
                            extra_data={
                                "attempt": attempt,
                                "elapsed_time": elapsed_time,
                            },
                        )
                        raise e

                    print(
                        f"API call failed (attempt {attempt}), retrying in {delay} seconds..."
                    )
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

    if response.status_code != 200:
        print("Error login.")
        print(response)
        rollbar.report_message(
            "Error logging in", extra_data={"response": response.json()}
        )
        raise Exception("Error logging in")

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
        print("Error getting parameters")
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

    if response.status_code != 200:
        print("Error patching execution")
        rollbar.report_message(
            "Error patching execution", extra_data={"response": response.json()}
        )
        print(response)


@retry_api_call(max_duration_minutes=10)
def save_log(json):
    jwt = login()
    response = requests.post(
        API_URL + "/api/v1/execution/" + EXECUTION_ID + "/log",
        json=json,
        headers={"Authorization": "Bearer " + jwt},
    )

    if response.status_code != 200:
        print("Error saving log")
        rollbar.report_message(
            "Error saving log", extra_data={"response": response.json()}
        )
        print(response)
