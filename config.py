"""Centralized configuration using pydantic-settings.

All settings are loaded from environment variables with ``.env`` file support.
Import ``settings`` from this module to access validated configuration.
Fails fast at import time if required API keys are missing.

Usage::

    from config import settings
    print(settings.model_name)
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from exceptions import ConfigError


class Settings(BaseSettings):
    """Application settings — validated at import time."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore unknown env vars
    )

    # ── Required API keys ─────────────────────────────────────────────────
    groq_api_key: str = Field(
        ..., description="API key for Groq LLM provider"
    )
    tavily_api_key: str = Field(
        ..., description="API key for Tavily search"
    )

    # ── Model configuration ───────────────────────────────────────────────
    model_name: str = Field(
        default="llama-3.1-8b-instant",
        description="Groq model identifier",
    )
    model_temperature: float = Field(
        default=0.0, ge=0.0, le=2.0,
        description="LLM temperature (0 = deterministic)",
    )

    # ── Search configuration ──────────────────────────────────────────────
    search_max_results: int = Field(
        default=3, ge=1, le=20,
        description="Maximum number of Tavily search results",
    )

    # ── Scraping configuration ────────────────────────────────────────────
    scrape_max_chars: int = Field(
        default=3000, ge=100,
        description="Maximum characters to extract per scraped page",
    )
    scrape_timeout_seconds: int = Field(
        default=10, ge=1, le=60,
        description="HTTP request timeout for scraping",
    )
    scrape_parallel_count: int = Field(
        default=3, ge=1, le=10,
        description="Number of URLs to scrape in parallel",
    )
    scrape_retry_attempts: int = Field(
        default=2, ge=0, le=5,
        description="Number of retry attempts for failed scrapes",
    )

    # ── Context limits ────────────────────────────────────────────────────
    search_context_max_chars: int = Field(
        default=800, ge=100,
        description="Max chars of search results passed to reader agent",
    )

    # ── Cache configuration ───────────────────────────────────────────────
    cache_enabled: bool = Field(
        default=True,
        description="Enable disk caching for search/scrape results",
    )
    cache_search_ttl_seconds: int = Field(
        default=600, ge=0,
        description="Cache TTL for search results (default: 10 minutes)",
    )
    cache_scrape_ttl_seconds: int = Field(
        default=1800, ge=0,
        description="Cache TTL for scraped pages (default: 30 minutes)",
    )

    # ── Security ──────────────────────────────────────────────────────────
    scrape_allowed_schemes: tuple[str, ...] = ("http", "https")
    scrape_blocked_hosts: tuple[str, ...] = (
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "169.254.169.254",       # AWS metadata
        "metadata.google.internal",  # GCP metadata
    )

    @field_validator("groq_api_key", "tavily_api_key")
    @classmethod
    def _must_not_be_placeholder(cls, v: str, info) -> str:
        """Reject placeholder values from .env.example."""
        placeholders = {"your_groq_api_key_here", "your_tavily_api_key_here", ""}
        if v in placeholders:
            raise ConfigError(
                f"{info.field_name} is not set. "
                "Copy .env.example to .env and fill in your API keys.",
                user_message=f"Missing API key: {info.field_name}. "
                "Please set it in your .env file.",
            )
        return v


def _load_settings() -> Settings:
    """Load and validate settings. Raises ConfigError on failure."""
    try:
        return Settings()  # type: ignore[call-arg]
    except Exception as e:
        raise ConfigError(
            f"Failed to load configuration: {e}",
            user_message="Configuration error. Check your .env file.",
        ) from e


settings = _load_settings()
