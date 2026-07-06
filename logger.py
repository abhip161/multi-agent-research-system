"""Centralized logging configuration for ResearchMind.

Usage:
    from logger import setup_logging, get_logger

    setup_logging()  # Call once at app startup
    logger = get_logger(__name__)  # Use in each module
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path


# ── Constants ─────────────────────────────────────────────────────────────────

_LOG_FORMAT = "%(asctime)s  %(name)-24s  %(levelname)-8s  %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_LOG_FILE = Path(__file__).resolve().parent / "research_mind.log"

_initialized = False


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the root logger with console and file handlers.

    Safe to call multiple times — subsequent calls are no-ops.
    Console output goes to stderr so it doesn't interfere with
    Streamlit's stdout-based rendering.

    Args:
        level: Logging level (default: INFO).
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    root = logging.getLogger()
    root.setLevel(level)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT)

    # Console handler — stderr to avoid Streamlit conflicts
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(level)
    console.setFormatter(formatter)
    root.addHandler(console)

    # File handler — captures everything for debugging
    try:
        file_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        # If we can't write log files (e.g., read-only filesystem), continue
        root.warning("Could not create log file at %s", _LOG_FILE)

    # Silence overly chatty libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("langchain").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a named logger. Ensures logging is initialized first.

    Args:
        name: Logger name (typically ``__name__``).

    Returns:
        Configured logger instance.
    """
    setup_logging()
    return logging.getLogger(name)
