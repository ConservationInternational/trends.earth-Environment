"""The GEF CORE Module."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import sys
import os
import logging
import base64
import json

from gefcore.runner import run

import rollbar
from rollbar.logger import RollbarHandler

# From:
# https://stackoverflow.com/questions/6234405/logging-uncaught-exceptions-in-python
logger = logging.getLogger(__name__)
handler = logging.StreamHandler(stream=sys.stdout)
logger.addHandler(handler)

rollbar.init(os.getenv('ROLLBAR_SCRIPT_TOKEN'), os.getenv('ENV'))
rollbar_handler = RollbarHandler()
rollbar_handler.setLevel(logging.ERROR)
logger.addHandler(rollbar_handler)

def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = handle_exception

logger.setLevel(logging.DEBUG)


params = {}
if len(sys.argv) > 1:
    query = sys.argv[1][1:]
    params = base64.b64decode(query)
    params = params.decode('utf-8')
    params = json.loads(params)

# TODO: read parameters from a json file rather than from sys.argv
# params_file = os.path.join(
#     os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
#     'params.json'
# )
# with open(params_file, 'r') as f:
#     params = json.load(f)

run(params)
