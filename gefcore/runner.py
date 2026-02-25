"""GEF CORE RUNNER"""

import contextlib
import logging
import os

import ee
import rollbar

from gefcore.api import get_params, patch_execution
from gefcore.loggers import get_logger

try:
    from gefcore.script import main
except ImportError:
    main = None

# Note: Rollbar is already initialized in gefcore/__init__.py.
# We only need access to the rollbar module here for reporting - no need to re-init.
rollbar_token = os.getenv("ROLLBAR_SCRIPT_TOKEN")

# Silence warning about file_cache being unavailable. See more here:
# https://github.com/googleapis/google-api-python-client/issues/299
logging.getLogger("googleapiclient").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("google_auth_httplib2").setLevel(logging.ERROR)

logger = get_logger(__name__)

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = os.getenv("ENV")
GOOGLE_PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID")
GEE_ENDPOINT = os.getenv("GEE_ENDPOINT")


def initialize_earth_engine():
    """Initialize Google Earth Engine with available credentials (OAuth or service account)."""
    logger.info("Starting Earth Engine initialization...")

    # Try OAuth credentials first (if available)
    if os.getenv("GEE_OAUTH_ACCESS_TOKEN") and os.getenv("GEE_OAUTH_REFRESH_TOKEN"):
        logger.info("Found OAuth credentials, attempting OAuth authentication...")
        if _initialize_ee_with_oauth():
            logger.info("Successfully authenticated with Earth Engine using OAuth")
            return
        logger.warning("OAuth authentication failed, falling back to service account")

    # Fall back to service account authentication
    if os.getenv("EE_SERVICE_ACCOUNT_JSON") or _has_service_account_file():
        logger.info("Attempting service account authentication...")
        if _initialize_ee_with_service_account():
            logger.info(
                "Successfully authenticated with Earth Engine using service account"
            )
            return

    # No credentials available
    from gefcore import _get_rollbar_extra_data

    error_msg = "No Google Earth Engine credentials available. Please provide either OAuth tokens or service account credentials."
    logger.error(error_msg)
    extra_data = _get_rollbar_extra_data()
    extra_data.update(
        {
            "oauth_available": bool(os.getenv("GEE_OAUTH_ACCESS_TOKEN")),
            "service_account_available": bool(
                os.getenv("EE_SERVICE_ACCOUNT_JSON") or _has_service_account_file()
            ),
            "error_location": "initialize_earth_engine",
        }
    )
    rollbar.report_message(
        "Missing GEE credentials",
        extra_data=extra_data,
    )
    raise RuntimeError(error_msg)


def _has_service_account_file():
    """Check if service account file exists."""
    service_account_path = os.path.join(PROJECT_DIR, "service_account.json")
    return os.path.exists(service_account_path)


def _initialize_ee_with_oauth():
    """Initialize Google Earth Engine with OAuth credentials."""
    try:
        from google.oauth2.credentials import Credentials

        # Create OAuth credentials from environment variables
        credentials = Credentials(
            token=os.getenv("GEE_OAUTH_ACCESS_TOKEN"),
            refresh_token=os.getenv("GEE_OAUTH_REFRESH_TOKEN"),
            token_uri=os.getenv(
                "GOOGLE_OAUTH_TOKEN_URI", "https://oauth2.googleapis.com/token"
            ),
            client_id=os.getenv("GOOGLE_OAUTH_CLIENT_ID"),
            client_secret=os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"),
            scopes=["https://www.googleapis.com/auth/earthengine"],
        )

        # Initialize Earth Engine with OAuth credentials
        ee.Initialize(credentials, project=GOOGLE_PROJECT_ID, opt_url=GEE_ENDPOINT)
        logger.info("Earth Engine OAuth authentication successful")
        return True

    except ImportError as e:
        logger.error(f"OAuth dependencies not available: {e}")
        return False
    except Exception as e:
        import traceback

        from gefcore import _get_rollbar_extra_data

        full_traceback = traceback.format_exc()
        logger.error(
            f"Failed to initialize Earth Engine with OAuth: {e}\n\nFull traceback:\n{full_traceback}"
        )
        extra_data = _get_rollbar_extra_data()
        extra_data.update(
            {
                "oauth_client_id": os.getenv("GOOGLE_OAUTH_CLIENT_ID") is not None,
                "error_location": "_initialize_ee_with_oauth",
            }
        )
        rollbar.report_exc_info(extra_data=extra_data)
        return False


def _initialize_ee_with_service_account():
    """Initialize Google Earth Engine with service account credentials."""
    try:
        # Try environment variable first (base64 encoded JSON)
        service_account_json = os.getenv("EE_SERVICE_ACCOUNT_JSON")
        if service_account_json:
            logger.info("Using service account from environment variable")
            import base64
            import json
            import tempfile

            # Decode base64 service account JSON
            try:
                decoded_json = base64.b64decode(service_account_json).decode("utf-8")
                service_account_data = json.loads(decoded_json)
            except Exception as e:
                logger.error(
                    f"Failed to decode service account JSON from environment: {e}"
                )
                return False

            # Write to temporary file for Earth Engine
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            ) as temp_file:
                json.dump(service_account_data, temp_file)
                temp_key_path = temp_file.name

            try:
                service_account_data = json.loads(decoded_json)
                gee_credentials = ee.ServiceAccountCredentials(
                    email=service_account_data.get("client_email"),
                    key_file=temp_key_path,
                )
                ee.Initialize(
                    gee_credentials, project=GOOGLE_PROJECT_ID, opt_url=GEE_ENDPOINT
                )
                logger.info(
                    "Earth Engine service account authentication successful (from environment)"
                )
                return True
            finally:
                # Clean up temporary file
                with contextlib.suppress(Exception):
                    os.unlink(temp_key_path)

        # Fall back to file-based service account
        service_account_path = os.path.join(PROJECT_DIR, "service_account.json")
        if os.path.exists(service_account_path):
            logger.info(f"Using service account file at: {service_account_path}")

            # Read service account data to get email
            try:
                with open(service_account_path) as f:
                    service_account_data = json.load(f)

                gee_credentials = ee.ServiceAccountCredentials(
                    email=service_account_data.get("client_email"),
                    key_file=service_account_path,
                )
                ee.Initialize(
                    gee_credentials, project=GOOGLE_PROJECT_ID, opt_url=GEE_ENDPOINT
                )
                logger.info(
                    "Earth Engine service account authentication successful (from file)"
                )
                return True
            except Exception as e:
                logger.error(f"Failed to read or use service account file: {e}")
                return False

        logger.error("No service account credentials found")
        return False

    except Exception as e:
        import traceback

        from gefcore import _get_rollbar_extra_data

        full_traceback = traceback.format_exc()
        logger.error(
            f"Failed to initialize Earth Engine with service account: {e}\n\nFull traceback:\n{full_traceback}"
        )
        extra_data = _get_rollbar_extra_data()
        extra_data.update(
            {
                "service_account_file_exists": _has_service_account_file(),
                "service_account_env_available": bool(
                    os.getenv("EE_SERVICE_ACCOUNT_JSON")
                ),
                "error_location": "_initialize_ee_with_service_account",
            }
        )
        rollbar.report_exc_info(extra_data=extra_data)
        return False


def change_status_ticket(status):
    """Ticket status changer.

    Exceptions are caught and logged when setting terminal statuses (FAILED,
    CANCELLED) so that an API communication failure does not prevent the
    caller from continuing or leave the execution stuck in RUNNING state.
    """
    if ENV != "dev":
        try:
            patch_execution(json={"status": status})
        except Exception as exc:
            logger.error(f"Failed to set execution status to {status}: {exc}")
            # For terminal statuses the best we can do is report to Rollbar
            # and let the stale-execution cleanup task on the API handle it.
            if status in ("FAILED", "CANCELLED"):
                import sys

                print(
                    f"CRITICAL: Could not set execution status to {status}: {exc}",
                    file=sys.stderr,
                )
                # Re-raise for non-terminal statuses (e.g. RUNNING) since
                # those are called during setup and should abort execution.
            else:
                raise
    else:
        logger.info(f"Changing to {status}")


def send_result(results):
    """Results sender"""
    if ENV != "dev":
        patch_execution(json={"results": results, "status": "FINISHED"})
    else:
        logger.info(f"Finished -> Results: {results}")


def run():
    """Runs the user script"""
    from gefcore import _get_rollbar_extra_data

    git_sha = os.getenv("GIT_SHA", "unknown")
    logger.info(f"Starting execution (trends.earth-Environment git SHA: {git_sha}, EE API {ee.__version__})")

    try:
        initialize_earth_engine()

        # Set a global HTTP timeout for all EE API calls so they never block
        # forever.  Without this, any transient network issue can cause the
        # process to hang indefinitely (timeout defaults to 0 = unlimited).
        # 120 000 ms = 2 minutes — generous enough for any single API
        # round-trip while still preventing indefinite hangs.
        ee.data.setDeadline(120_000)
        logger.info("EE initialized, deadline set to 120s")

        change_status_ticket("RUNNING")
        params = get_params()
        logger.info("Parameters retrieved, running script...")
        if params is not None:
            params["ENV"] = os.getenv("ENV", None)
            params["EXECUTION_ID"] = os.getenv("EXECUTION_ID", None)
        else:
            params = {}
            params["ENV"] = os.getenv("ENV", None)
            params["EXECUTION_ID"] = os.getenv("EXECUTION_ID", None)

        if main is None:
            raise ImportError("gefcore.script.main module not found")

        result = main.run(params, logger)
        logger.info("Execution completed successfully")

        send_result(result)
    except Exception as error:
        import traceback

        full_traceback = traceback.format_exc()
        logger.error(
            f"Script execution failed: {error}\n\nFull traceback:\n{full_traceback}"
        )

        change_status_ticket("FAILED")

        # Report to Rollbar with full context
        extra_data = _get_rollbar_extra_data()
        extra_data["error_location"] = "runner.run()"
        extra_data["error_type"] = type(error).__name__
        extra_data["error_message"] = str(error)[:1000]
        rollbar.report_exc_info(extra_data=extra_data)
        raise
