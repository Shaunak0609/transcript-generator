"""
Logging configuration for the AI Video Transcriber.

Initialise once with setup_logging() at the start of main().
Every other module calls get_logger() to retrieve the shared logger.

Console verbosity is controlled by CLI flags:

  (default)  INFO    — progress banners + status lines
  --verbose  DEBUG   — also shows timing, word/segment counts, output paths
  --debug    DEBUG   — same as --verbose; tracebacks handled separately in cli
  --quiet    WARNING — silent unless there is a warning or error

ERROR and CRITICAL are excluded from the console handler so they are never
duplicated; cli._print_error() is responsible for writing errors to stderr.
The file handler always captures DEBUG and above regardless of flags.

Log files are written to  logs/transcriber_YYYY-MM-DD_HH-MM-SS.log
"""

import logging
import os
from datetime import datetime

_LOGGER_NAME = "transcriber"
_LOG_DIR = "logs"


class _ConsoleFormatter(logging.Formatter):
    """
    Minimal formatter that keeps terminal output identical to the previous
    print-based output:

      INFO    → bare message  (no prefix, no timestamp)
      DEBUG   → [DEBUG] message
      WARNING → [WARNING] message

    Section-header messages (those starting with '---') automatically get a
    blank line prepended so visual sections are separated, just as the old
    print("\\n--- ... ---") calls did.
    """

    def format(self, record):
        msg = record.getMessage()

        if record.levelno == logging.DEBUG:
            formatted = f"[DEBUG] {msg}"
        elif record.levelno == logging.WARNING:
            formatted = f"[WARNING] {msg}"
        else:
            formatted = msg

        if msg.startswith("---"):
            return "\n" + formatted
        return formatted


class _BelowErrorFilter(logging.Filter):
    """Allow only records with level < ERROR through the console handler.

    Errors are printed to stderr by cli._print_error() so they never appear
    twice in the terminal.
    """

    def filter(self, record):
        return record.levelno < logging.ERROR


def setup_logging(quiet=False, verbose=False, debug=False):
    """Configure the transcriber logger and return (logger, log_file_path).

    Creates the logs/ directory if it does not exist.  Falls back to
    console-only logging (with a warning) if the log file cannot be created.
    """
    logger = logging.getLogger(_LOGGER_NAME)

    # Idempotent — skip if handlers already attached (e.g. during testing)
    if logger.handlers:
        return logger, None

    logger.setLevel(logging.DEBUG)

    log_path = None

    # ── File handler — DEBUG and above, full timestamp format ────────────────
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_path = os.path.join(_LOG_DIR, f"transcriber_{ts}.log")

        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            fmt="%(asctime)s [%(levelname)-8s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(fh)
    except OSError:
        log_path = None  # fall through to console-only mode

    # ── Console handler — stdout, level based on flags, errors excluded ───────
    if debug or verbose:
        console_level = logging.DEBUG
    elif quiet:
        console_level = logging.WARNING
    else:
        console_level = logging.INFO

    ch = logging.StreamHandler()  # stdout
    ch.setLevel(console_level)
    ch.addFilter(_BelowErrorFilter())
    ch.setFormatter(_ConsoleFormatter())
    logger.addHandler(ch)

    if log_path is None:
        logger.warning(
            f"Could not create log directory '{_LOG_DIR}'. "
            "Logging to console only."
        )

    return logger, log_path


def get_logger():
    """Return the application logger.  setup_logging() must have been called first."""
    return logging.getLogger(_LOGGER_NAME)
