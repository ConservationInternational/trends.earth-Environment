"""GEF CORE LOGGER"""

import logging
import os

from gefcore.api import patch_execution, save_log


class GEFLogger(logging.Logger):
    """Custom logger class with send_progress method."""
    
    def send_progress(self, progress):
        """Send script execution progress."""
        env = os.getenv("ENV", "dev")
        if env == "prod":
            patch_execution(json={"progress": progress})
        else:
            self.info(f"Progress: {progress}%")


class ServerLogHandler(logging.Handler):
    """A logging handler that sends logs to the server via API calls."""

    def emit(self, record):
        """Sends the log record to the server."""
        try:
            log_entry = {"text": self.format(record), "level": record.levelname}
            save_log(json=log_entry)
        except Exception:
            self.handleError(record)


def get_logger(name=None):
    """
    Get a logger configured for the current environment (dev or prod).

    In 'prod', it uses ServerLogHandler to send logs to the API.
    In 'dev', it logs to the console.
    """
    # Set the logger class to our custom GEFLogger
    logging.setLoggerClass(GEFLogger)
    
    env = os.getenv("ENV", "dev")
    logger = logging.getLogger(name or "gefcore")
    logger.setLevel(logging.DEBUG)

    if logger.hasHandlers():
        logger.handlers.clear()

    if env == "prod":
        handler = ServerLogHandler()
        formatter = logging.Formatter("%(message)s")
        handler.setFormatter(formatter)
    else:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)

    logger.addHandler(handler)

    return logger
