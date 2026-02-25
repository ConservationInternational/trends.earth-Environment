"""The GEF CORE Module."""

import logging
import os
import sys

import rollbar
from rollbar.logger import RollbarHandler

# From:
# https://stackoverflow.com/questions/6234405/logging-uncaught-exceptions-in-python
logger = logging.getLogger(__name__)
handler = logging.StreamHandler(stream=sys.stderr)
handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(handler)

# The API passes ROLLBAR_SCRIPT_TOKEN to the container (with its own fallback
# to ROLLBAR_SERVER_TOKEN already applied).  The Environment only needs this
# single token to separate script-execution errors from API-server errors.
rollbar_token = os.getenv("ROLLBAR_SCRIPT_TOKEN")
env = os.getenv("ENV")
execution_id = os.getenv("EXECUTION_ID")

if rollbar_token and env and env not in ("test", "testing"):
    rollbar.init(rollbar_token, env)
    rollbar_handler = RollbarHandler()
    rollbar_handler.setLevel(logging.WARNING)  # Only send WARNING and above to Rollbar
    logger.addHandler(rollbar_handler)


def _get_rollbar_extra_data():
    """
    Get standard extra_data dict for Rollbar reports from Environment.

    Includes source identification and execution context to help differentiate
    from API reports and enable grouping of related errors.
    """
    return {
        "source": "trends.earth-environment",
        "execution_id": os.getenv("EXECUTION_ID"),
        "env": os.getenv("ENV"),
    }


def handle_exception(exc_type, exc_value, exc_traceback):
    """Handle uncaught exceptions by logging them."""
    if issubclass(exc_type, KeyboardInterrupt):
        logger.warning("Execution interrupted by user")
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    # Get detailed traceback information
    import traceback

    tb_details = traceback.format_exception(exc_type, exc_value, exc_traceback)
    tb_string = "".join(tb_details)

    # Log with full traceback details
    logger.error(
        f"Uncaught exception occurred: {exc_value}\n\nFull traceback:\n{tb_string}",
        exc_info=(exc_type, exc_value, exc_traceback),
    )

    # Also report to Rollbar with full exception info and source identification
    # Note: RollbarHandler may also report this via logger.error above, but
    # we include extra_data here for richer context in Rollbar
    if rollbar_token and os.getenv("ENV") not in ("test", "testing"):
        extra_data = _get_rollbar_extra_data()
        extra_data["exception_type"] = exc_type.__name__
        extra_data["exception_message"] = str(exc_value)[
            :500
        ]  # Truncate large messages
        rollbar.report_exc_info(
            exc_info=(exc_type, exc_value, exc_traceback),
            extra_data=extra_data,
        )


sys.excepthook = handle_exception

logger.setLevel(logging.DEBUG)


# Only run if not in test environment and TESTING is not set
# Also check if we're running under pytest
is_pytest = "pytest" in sys.modules or "pytest" in sys.argv[0] if sys.argv else False
should_run = (
    os.getenv("ENV") not in ("test", "testing")
    and not os.getenv("TESTING")
    and not is_pytest
)

if should_run:
    try:
        from gefcore.runner import run

        run()
    except ImportError as e:
        logger.warning(f"Could not import runner: {e}")
        sys.exit(1)
    except FileNotFoundError as e:
        logger.warning(f"Service account file not found: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error running main script: {e}")
        sys.exit(1)
    else:
        # Explicit clean exit so the process terminates immediately.
        # Without this, cleanup during interpreter shutdown can
        # produce a non-zero exit code, which (with a Swarm
        # "on-failure" restart policy) would cause the container to
        # be rescheduled — re-running an already-finished execution.
        sys.exit(0)
