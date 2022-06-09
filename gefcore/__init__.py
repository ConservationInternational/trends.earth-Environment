"""The GEF CORE Module."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import logging
import os
import sys

import rollbar
from gefcore.runner import run
from rollbar.logger import RollbarHandler

# From:
# https://stackoverflow.com/questions/6234405/logging-uncaught-exceptions-in-python
logger = logging.getLogger(__name__)
handler = logging.StreamHandler(stream=sys.stdout)
logger.addHandler(handler)

rollbar.init(os.getenv('ROLLBAR_SCRIPT_TOKEN'), os.getenv('ENV'))
rollbar_handler = RollbarHandler()
rollbar_handler.setLevel(logging.INFO)
logger.addHandler(rollbar_handler)


def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

        return
    logger.critical("Uncaught exception",
                    exc_info=(exc_type, exc_value, exc_traceback))


sys.excepthook = handle_exception

logger.setLevel(logging.DEBUG)

run()
