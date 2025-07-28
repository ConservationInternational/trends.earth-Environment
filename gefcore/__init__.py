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

rollbar.init(os.getenv("ROLLBAR_SCRIPT_TOKEN"), os.getenv("ENV"))
rollbar_handler = RollbarHandler()
rollbar_handler.setLevel(logging.INFO)
logger.addHandler(rollbar_handler)


def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

        return
    logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))


sys.excepthook = handle_exception

logger.setLevel(logging.DEBUG)

# Only run if not in test environment
if os.getenv("ENV") != "test":
    try:
        from gefcore.runner import run

        run()
    except ImportError as e:
        logger.warning(f"Could not import runner: {e}")
    except FileNotFoundError as e:
        logger.warning(f"Service account file not found: {e}")
    except Exception as e:
        logger.error(f"Error running main script: {e}")
