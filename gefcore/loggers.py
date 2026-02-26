"""GEF CORE LOGGER"""

import logging
import os
from contextlib import suppress

from gefcore.api import patch_execution, save_log


class GEFLogger(logging.Logger):
    """Custom logger class with send_progress method."""

    def send_progress(self, progress):
        """Send script execution progress."""
        env = os.getenv("ENV", "dev")
        if env in ("prod", "production"):
            patch_execution(json={"progress": progress})
        else:
            self.info(f"Progress: {progress}%")


class _NoOpLock:
    """A lock that never blocks — satisfies the logging.Handler lock protocol."""

    def acquire(self):
        pass

    def release(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class ServerLogHandler(logging.Handler):
    """A logging handler that sends logs to the server via API calls.

    Calls ``save_log`` synchronously inside ``emit()``.  The call is
    fire-and-forget: if it fails the exception is caught and the message
    is already on stderr (the stderr handler runs first).

    The handler lock is disabled (``createLock`` sets it to ``None``)
    so that a slow or failing ``save_log`` call in one thread cannot
    block other threads from logging.  Each ``emit`` makes an
    independent HTTP request with no shared mutable state.
    """

    def createLock(self):  # noqa: N802 — overrides stdlib method name
        """Use a non-blocking lock so emit() never blocks other threads."""
        self.lock = _NoOpLock()

    def emit(self, record):
        """Send the log record to the server."""
        # Skip internal API-transport messages to avoid recursion:
        # save_log → _handle_api_error → logger.error → ServerLogHandler …
        if record.name.startswith("gefcore.api"):
            return

        try:
            formatted_message = self.format(record)

            # Include full traceback if present
            if record.exc_info and record.exc_info != (None, None, None):
                import traceback

                exc_text = traceback.format_exception(*record.exc_info)
                formatted_message += f"\n\nException details:\n{''.join(exc_text)}"

            # Truncate to stay within the API's 10 KB limit
            max_log_length = 9000
            if len(formatted_message) > max_log_length:
                formatted_message = (
                    formatted_message[:max_log_length]
                    + "\n\n[LOG TRUNCATED - MESSAGE TOO LONG]"
                )

            level = record.levelname.upper()
            if level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
                level = "INFO"

            log_entry = {"text": str(formatted_message), "level": level}
            save_log(json=log_entry)

        except Exception:
            # save_log already printed diagnostics to stderr via
            # _handle_api_error; just let handleError note it and move on.
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
        for existing_handler in logger.handlers:
            with suppress(Exception):
                existing_handler.close()
        logger.handlers.clear()

    api_logger = logging.getLogger("gefcore.api")
    if api_logger.hasHandlers():
        for existing_handler in api_logger.handlers:
            with suppress(Exception):
                existing_handler.close()
        api_logger.handlers.clear()
    api_logger.propagate = False
    api_handler = logging.StreamHandler()
    api_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    api_logger.addHandler(api_handler)
    if env in ("prod", "production"):
        api_logger.setLevel(logging.INFO)
    else:
        api_logger.setLevel(logging.DEBUG)

    # Prevent messages from propagating to the parent "gefcore" logger
    # (which has its own stderr + Rollbar handlers in __init__.py).
    # Without this, every message would appear twice on stderr.
    logger.propagate = False

    if env in ("prod", "production"):
        # First: write to stderr so that Docker container logs always
        # capture output instantly, even when the API is unreachable
        # (expired auth, network issues, etc.).  Handlers are called in
        # order, so putting this first ensures the message reaches
        # container logs before the potentially-blocking API call.
        stderr_handler = logging.StreamHandler()
        stderr_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        )
        stderr_handler.setFormatter(stderr_formatter)
        logger.addHandler(stderr_handler)

        # Second: send logs to the API so they appear in the execution
        # log visible from the UI.  If this handler blocks (due to auth
        # refresh retries), stderr has already received the message.
        server_handler = ServerLogHandler()
        server_formatter = logging.Formatter("%(message)s")
        server_handler.setFormatter(server_formatter)
        logger.addHandler(server_handler)

        # Third: forward WARNING+ to Rollbar so exceptions and errors
        # are always captured even with propagate=False.  Rollbar is
        # already initialized by gefcore.__init__ before get_logger()
        # is called, so the handler will work immediately.
        rollbar_token = os.getenv("ROLLBAR_SCRIPT_TOKEN")
        if rollbar_token:
            from rollbar.logger import RollbarHandler

            rollbar_handler = RollbarHandler()
            rollbar_handler.setLevel(logging.WARNING)
            logger.addHandler(rollbar_handler)
    else:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
