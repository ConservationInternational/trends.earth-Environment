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
            # Include exception info if present
            formatted_message = self.format(record)
            
            # If there's exception info, include the full traceback
            if record.exc_info and record.exc_info != (None, None, None):
                import traceback
                exc_text = traceback.format_exception(*record.exc_info)
                exc_string = "".join(exc_text)
                formatted_message += f"\n\nException details:\n{exc_string}"
            
            log_entry = {"text": formatted_message, "level": record.levelname}
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
