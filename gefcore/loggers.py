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

            # Truncate message if too long to prevent API 400 errors
            # API has a 10KB limit, so truncate at 9KB to be safe
            max_log_length = 9000
            if len(formatted_message) > max_log_length:
                truncated_msg = formatted_message[:max_log_length]
                formatted_message = (
                    truncated_msg + "\n\n[LOG TRUNCATED - MESSAGE TOO LONG]"
                )

            log_entry = {"text": formatted_message, "level": record.levelname}

            # Validate log entry before sending to catch issues early
            if not isinstance(log_entry["text"], str):
                log_entry["text"] = str(log_entry["text"])
            if not isinstance(log_entry["level"], str):
                log_entry["level"] = str(log_entry["level"])

            # Ensure level is uppercase and valid
            valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            log_entry["level"] = log_entry["level"].upper()
            if log_entry["level"] not in valid_levels:
                # Default to INFO if level is invalid
                log_entry["level"] = "INFO"

            save_log(json=log_entry)
        except Exception as e:
            # Log the error details for debugging, but don't let it crash the application
            try:
                # Try to get some info about what went wrong
                error_msg = f"Failed to save log entry: {str(e)}"
                # Check if it's a requests exception with response info
                if hasattr(e, "__dict__") and "response" in e.__dict__:
                    response = e.__dict__["response"]  # type: ignore
                    if hasattr(response, "status_code"):
                        error_msg += f" (HTTP {response.status_code})"  # type: ignore
                        if hasattr(response, "text"):
                            error_msg += f" - {response.text[:200]}"  # type: ignore

                # Fall back to standard error handling
                self.handleError(record)

                # Also try to print to stderr as a last resort
                import sys

                print(f"Logger error: {error_msg}", file=sys.stderr)
            except Exception:
                # If even error reporting fails, use the standard handler
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
