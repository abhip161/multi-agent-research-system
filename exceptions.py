"""Custom exception hierarchy for ResearchMind.

All exceptions inherit from ``ResearchMindError`` so callers can
catch the base class for generic error handling, or specific
subclasses for targeted recovery.

Each exception carries a ``user_message`` that is safe to display
in the UI, and preserves the original exception via ``__cause__``.
"""

from __future__ import annotations


class ResearchMindError(Exception):
    """Base exception for all ResearchMind errors."""

    def __init__(self, message: str, user_message: str | None = None) -> None:
        super().__init__(message)
        # user_message is safe to display in the UI; falls back to message
        self.user_message = user_message or message


class ConfigError(ResearchMindError):
    """Raised when required configuration is missing or invalid."""


class SearchError(ResearchMindError):
    """Raised when the web search step fails."""


class ScrapeError(ResearchMindError):
    """Raised when URL scraping fails."""


class WriterError(ResearchMindError):
    """Raised when the report writing step fails."""


class CriticError(ResearchMindError):
    """Raised when the critic review step fails."""


class ExportError(ResearchMindError):
    """Raised when report export (Markdown/PDF) fails."""
