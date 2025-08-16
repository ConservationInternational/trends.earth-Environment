"""The GEF CORE Module."""

import logging
import os
import sys

import rollbar
from rollbar.logger import RollbarHandler

# From:
# https://stackoverflow.com/questions/6234405/logging-uncaught-exceptions-in-python
logger = logging.getLogger(__name__)
handler = logging.StreamHandler(stream=sys.stdout)
logger.addHandler(handler)

rollbar_token = os.getenv("ROLLBAR_SCRIPT_TOKEN")
env = os.getenv("ENV")
if rollbar_token and env and env not in ("test", "testing"):
    rollbar.init(rollbar_token, env)
    rollbar_handler = RollbarHandler()
    rollbar_handler.setLevel(logging.INFO)
    logger.addHandler(rollbar_handler)


def handle_exception(exc_type, exc_value, exc_traceback):
    """Handle uncaught exceptions by logging them."""
    if issubclass(exc_type, KeyboardInterrupt):
        logger.warning("Execution interrupted by user")
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger.error(
        "Uncaught exception occurred",
        exc_info=(exc_type, exc_value, exc_traceback),
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
    except FileNotFoundError as e:
        logger.warning(f"Service account file not found: {e}")
    except Exception as e:
        logger.error(f"Error running main script: {e}")
