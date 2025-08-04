"""GEF CORE RUNNER"""

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

rollbar.init(os.getenv("ROLLBAR_SCRIPT_TOKEN"), os.getenv("ENV"))

# Silence warning about file_cache being unavailable. See more here:
# https://github.com/googleapis/google-api-python-client/issues/299
logging.getLogger("googleapiclient").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("google_auth_httplib2").setLevel(logging.ERROR)

logging.basicConfig(
    level="INFO",
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y%m%d-%H:%M%p",
)

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = os.getenv("ENV")
GOOGLE_PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID")
GEE_ENDPOINT = os.getenv("GEE_ENDPOINT")


def initialize_earth_engine():
    """Initialize Google Earth Engine with service account credentials."""
    logging.info("Starting Earth Engine initialization...")
    service_account_path = os.path.join(PROJECT_DIR, "service_account.json")
    logging.info(f"Looking for service account file at: {service_account_path}")

    if not os.path.exists(service_account_path):
        error_msg = f"Service account file not found at {service_account_path}. Google Earth Engine authentication is required."
        logging.error(error_msg)
        rollbar.report_message(
            "Missing GEE service account file",
            extra_data={"service_account_path": service_account_path},
        )
        raise FileNotFoundError(error_msg)

    try:
        logging.info("Authenticating earth engine...")
        gee_credentials = ee.ServiceAccountCredentials(
            email=None, key_file=service_account_path
        )
        logging.info("Earth Engine credentials created, initializing...")
        ee.Initialize(gee_credentials)
        # ee.Initialize(credentials=gee_credentials, project=GOOGLE_PROJECT_ID, opt_url=GEE_ENDPOINT)
        logging.info("Authenticated with earth engine.")
    except Exception as e:
        error_msg = f"Failed to initialize Earth Engine: {e}"
        logging.error(error_msg)
        rollbar.report_exc_info(
            extra_data={"service_account_path": service_account_path}
        )
        raise


def change_status_ticket(status):
    """Ticket status changer"""
    if ENV != "dev":
        patch_execution(json={"status": status})
    else:
        logging.info("Changing to RUNNING")


def send_result(results):
    """Results sender"""
    if ENV != "dev":
        patch_execution(json={"results": results, "status": "FINISHED"})
    else:
        logging.info("Finished -> Results:")
        logging.info(results)


def run():
    """Runs the user script"""
    logger = get_logger(__name__)
    logging.info("Starting run() function")
    try:
        logging.info("About to initialize Earth Engine...")
        # Initialize Earth Engine if needed
        initialize_earth_engine()
        logging.info("Earth Engine initialization completed successfully")

        logging.debug("Creating logger")
        # Getting logger
        logging.info("About to change status to RUNNING...")
        change_status_ticket("RUNNING")  # running
        logging.info("Status changed to RUNNING, now getting parameters...")
        params = get_params()
        logging.info("Parameters retrieved successfully")
        params["ENV"] = os.getenv("ENV", None)
        params["EXECUTION_ID"] = os.getenv("EXECUTION_ID", None)

        if main is None:
            raise ImportError("gefcore.script.main module not found")

        logging.info("About to run main script...")
        result = main.run(params, logger)
        logging.info("Main script completed, sending results...")
        send_result(result)
        logging.info("Results sent successfully")
    except Exception as error:
        logging.error(f"Error in run() function: {error}")
        change_status_ticket("FAILED")  # failed
        if logger:
            logger.error(str(error))
        rollbar.report_exc_info()
        raise error
