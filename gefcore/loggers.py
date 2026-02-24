"""GEF CORE LOGGER"""

import logging
import os
import sys
import threading

from gefcore.api import patch_execution, save_log


def _fire_and_forget(func, *args, **kwargs):
    """Run *func* in a daemon thread so the caller never blocks.

    If ``save_log`` or ``patch_execution`` trigger lengthy auth-retry
    loops (expired tokens → refresh retries → login retries) the calling
    thread would be blocked for minutes.  By delegating the call to a
    daemon thread the GEE polling thread keeps running normally.

    Daemon threads are automatically killed when the process exits, so
    queued-but-unfinished API calls are simply discarded — acceptable
    because the important messages are already on stderr.
    """
    t = threading.Thread(target=func, args=args, kwargs=kwargs, daemon=True)
    t.start()


class GEFLogger(logging.Logger):
    """Custom logger class with send_progress method."""

    def send_progress(self, progress):
        """Send script execution progress.

        The PATCH request is dispatched in a fire-and-forget daemon
        thread so that API failures (expired tokens, network issues,
        lengthy retry loops) never block the GEE task polling thread.
        """
        env = os.getenv("ENV", "dev")
        if env in ("prod", "production"):
            _fire_and_forget(self._do_send_progress, progress)
        else:
            self.info(f"Progress: {progress}%")

    # ------------------------------------------------------------------
    # Private helpers executed in daemon threads
    # ------------------------------------------------------------------

    @staticmethod
    def _do_send_progress(progress):
        try:
            patch_execution(json={"progress": progress})
        except Exception as exc:
            # stderr only — never call save_log here to avoid recursion.
            print(
                f"send_progress failed (progress={progress}): {exc}",
                file=sys.stderr,
            )


class ServerLogHandler(logging.Handler):
    """A logging handler that sends logs to the server via API calls.

    The actual HTTP POST (``save_log``) is dispatched to a fire-and-forget
    daemon thread so that the calling thread is never blocked — even when
    the API auth chain needs lengthy retries (refresh → login → backoff).
    All formatting and validation are done synchronously (cheap) before
    the async hand-off so that log records are captured correctly.
    """

    def emit(self, record):
        """Format the record synchronously, then POST it asynchronously."""
        try:
            log_entry = self._prepare_entry(record)
            _fire_and_forget(self._try_save, log_entry, record.getMessage())
        except Exception:
            self.handleError(record)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _prepare_entry(self, record):
        """Build the JSON payload to send to the API (runs in caller thread)."""
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

    @staticmethod
    def _try_save(log_entry, original_message):
        """POST the log entry to the API (runs in a daemon thread)."""
        try:
            save_log(json=log_entry)
        except Exception as e:
            try:
                error_msg = f"Failed to save log entry: {e}"
                if hasattr(e, "response") and hasattr(e.response, "status_code"):
                    error_msg += f" (HTTP {e.response.status_code})"
                print(f"Logger error: {error_msg}", file=sys.stderr)
                print(
                    f"Original log message that failed to send: {original_message}",
                    file=sys.stderr,
                )
            except Exception:  # noqa: S110
                pass  # Last resort — nothing more we can do


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
