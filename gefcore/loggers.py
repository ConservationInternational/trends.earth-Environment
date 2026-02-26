"""GEF CORE LOGGER"""

import logging
import os
import queue
import threading
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


class ServerLogHandler(logging.Handler):
    """A logging handler that sends logs to the server via API calls.

    Each ``emit()`` call posts the formatted log entry to the API
    synchronously.  Because Python's logging framework calls handlers
    in order, messages arrive at the API in the same order they were
    logged.  The stderr handler is always called first (added before
    this handler in ``get_logger``), so the message is captured in
    container logs even if the API call fails.
    """

    _emit_state = threading.local()

    def __init__(self, max_queue_size=1000):
        super().__init__()
        self._queue = queue.Queue(maxsize=max_queue_size)
        self._stop_event = threading.Event()
        self._worker = threading.Thread(
            target=self._drain_queue,
            name="server-log-handler-worker",
            daemon=True,
        )
        self._worker.start()

    def emit(self, record):
        """Format and enqueue the log entry for asynchronous POST."""
        if record.name.startswith("gefcore.api"):
            # Avoid recursive transport logging loops from save_log internals.
            return

        if getattr(self._emit_state, "active", False):
            return

        try:
            self._emit_state.active = True
            log_entry = self._prepare_entry(record)
            self._enqueue(log_entry, record)
        except Exception:
            self.handleError(record)
        finally:
            self._emit_state.active = False

    def _enqueue(self, log_entry, record):
        try:
            self._queue.put_nowait((log_entry, record))
        except queue.Full:
            # Drop oldest and keep newest to avoid blocking caller threads.
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                pass

            with suppress(queue.Full):
                self._queue.put_nowait((log_entry, record))

    def _drain_queue(self):
        while True:
            if self._stop_event.is_set() and self._queue.empty():
                return

            try:
                item = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if item is None:
                self._queue.task_done()
                continue

            log_entry, record = item
            try:
                save_log(json=log_entry)
            except Exception:
                self.handleError(record)
            finally:
                self._queue.task_done()

    def flush(self):
        self._queue.join()

    def close(self):
        self._stop_event.set()
        with suppress(queue.Full):
            self._queue.put_nowait(None)
        super().close()

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
