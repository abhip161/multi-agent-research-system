"""Tests for config.py — settings validation and fail-fast behavior."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest


class TestSettingsValidation:
    """Test that Settings validates required API keys."""

    def test_missing_groq_key_raises(self, monkeypatch):
        """Config should fail fast if GROQ_API_KEY is missing."""
        monkeypatch.setenv("GROQ_API_KEY", "")
        monkeypatch.setenv("TAVILY_API_KEY", "test-key")

        # Re-import to trigger validation
        from exceptions import ConfigError
        with pytest.raises((ConfigError, Exception)):
            from config import Settings
            Settings(groq_api_key="", tavily_api_key="test-key")

    def test_missing_tavily_key_raises(self, monkeypatch):
        """Config should fail fast if TAVILY_API_KEY is missing."""
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        monkeypatch.setenv("TAVILY_API_KEY", "")

        from exceptions import ConfigError
        with pytest.raises((ConfigError, Exception)):
            from config import Settings
            Settings(groq_api_key="test-key", tavily_api_key="")

    def test_placeholder_values_rejected(self, monkeypatch):
        """Config should reject placeholder values from .env.example."""
        from exceptions import ConfigError
        with pytest.raises((ConfigError, Exception)):
            from config import Settings
            Settings(
                groq_api_key="your_groq_api_key_here",
                tavily_api_key="test-key",
            )

    def test_valid_keys_accepted(self):
        """Config should accept valid API keys."""
        from config import Settings
        s = Settings(
            groq_api_key="gsk_real_key_12345",
            tavily_api_key="tvly-real_key_12345",
        )
        assert s.groq_api_key == "gsk_real_key_12345"
        assert s.tavily_api_key == "tvly-real_key_12345"

    def test_defaults(self):
        """Config should have sensible defaults for optional settings."""
        from config import Settings
        # Pass cache_enabled explicitly because conftest sets CACHE_ENABLED=false
        s = Settings(
            groq_api_key="test-key",
            tavily_api_key="test-key",
            cache_enabled=True,
        )
        assert s.model_name == "llama-3.1-8b-instant"
        assert s.model_temperature == 0.0
        assert s.search_max_results == 5
        assert s.scrape_max_chars == 3000
        assert s.scrape_timeout_seconds == 10
        assert s.scrape_parallel_count == 3
        assert s.cache_enabled is True

    def test_temperature_bounds(self):
        """Temperature should be between 0.0 and 2.0."""
        from config import Settings
        with pytest.raises(Exception):
            Settings(
                groq_api_key="test-key",
                tavily_api_key="test-key",
                model_temperature=3.0,  # Out of range
            )
