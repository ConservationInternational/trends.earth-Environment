"""GEF CORE LOGGER"""

import logging
import os
import queue
import sys
import threading

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


class ServerLogHandler(logging.Handler):
    """A logging handler that sends logs to the server via API calls.

    Log entries are enqueued synchronously (cheap) and a single daemon
    sender thread drains the queue in FIFO order.  This guarantees that:

    The sender thread is a daemon thread so it is killed automatically
    on process exit — any remaining queued entries are discarded, which
    is acceptable because all messages are always written to stderr first
    by the preceding handler in the chain.
    """

    _queue: queue.Queue = queue.Queue()
    _sender_thread: threading.Thread | None = None
    _lock: threading.Lock = threading.Lock()

    def emit(self, record):
        """Format the record synchronously, then enqueue for async POST."""
        try:
            log_entry = self._prepare_entry(record)
            ServerLogHandler._queue.put((log_entry, record.getMessage()))
            ServerLogHandler._ensure_sender_running()
        except Exception:
            self.handleError(record)

    # ------------------------------------------------------------------
    # Sender thread management
    # ------------------------------------------------------------------

    @classmethod
    def _ensure_sender_running(cls):
        """Start the sender thread if it is not already alive."""
        with cls._lock:
            if cls._sender_thread is None or not cls._sender_thread.is_alive():
                cls._sender_thread = threading.Thread(
                    target=cls._sender_loop, daemon=True
                )
                cls._sender_thread.start()

    @classmethod
    def _sender_loop(cls):
        """Drain the queue in order, one save_log() call at a time."""
        while True:
            log_entry, original_message = cls._queue.get()
            try:
                save_log(json=log_entry)
            except Exception as e:
                try:
                    error_msg = f"Failed to save log entry: {e}"
                    if hasattr(e, "response") and hasattr(
                        getattr(e, "response", None) or object(), "status_code"
                    ):
                        error_msg += f" (HTTP {e.response.status_code})"
                    print(f"Logger error: {error_msg}", file=sys.stderr)
                    print(
                        f"Original log message that failed to send: "
                        f"{original_message}",
                        file=sys.stderr,
                    )
                except Exception:  # noqa: S110
                    pass  # Last resort — nothing more we can do
            finally:
                cls._queue.task_done()

    # ------------------------------------------------------------------
    # Payload preparation (runs in caller thread)
    # ------------------------------------------------------------------

    def _prepare_entry(self, record):
        """Build the JSON payload to send to the API."""
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

        return {"text": str(formatted_message), "level": level}


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
