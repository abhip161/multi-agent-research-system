"""Shared fixtures for ResearchMind tests.

All external API calls (Tavily, Groq, HTTP requests) are mocked
to ensure tests are fast, deterministic, and free.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ── Mock settings to avoid requiring real API keys in tests ───────────────────

@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Set required env vars so config.py doesn't fail during tests."""
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key-12345")
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily-key-12345")
    monkeypatch.setenv("CACHE_ENABLED", "false")  # Disable cache in tests


@pytest.fixture
def sample_tavily_response():
    """Mock Tavily API response with realistic search results."""
    return {
        "results": [
            {
                "title": "AI Breakthroughs in 2025",
                "url": "https://example.com/ai-2025",
                "content": "Recent advances in artificial intelligence have led to...",
            },
            {
                "title": "The Future of LLM Agents",
                "url": "https://example.com/llm-agents",
                "content": "Large language model agents are transforming...",
            },
            {
                "title": "Multi-Agent Systems Overview",
                "url": "https://example.com/multi-agent",
                "content": "Multi-agent systems coordinate multiple AI agents...",
            },
        ]
    }


@pytest.fixture
def sample_html():
    """Sample HTML page for scraping tests."""
    return """
    <html>
    <head><title>Test Page</title></head>
    <body>
        <header><nav>Menu</nav></header>
        <main>
            <h1>Research Article</h1>
            <p>This is the main content of the article about AI research.</p>
            <p>It contains multiple paragraphs with useful information.</p>
        </main>
        <footer>Copyright 2025</footer>
        <script>alert('xss')</script>
        <style>.hidden { display: none; }</style>
    </body>
    </html>
    """


@pytest.fixture
def sample_report_text():
    """Sample research report text for writer/critic tests."""
    return """## Introduction
Artificial intelligence has seen remarkable progress in 2025.

## Key Findings
1. **LLM Agents**: Multi-agent systems are becoming more capable.
2. **Scaling Laws**: New research shows improved efficiency at scale.
3. **Safety**: Alignment techniques have matured significantly.

## Conclusion
The field continues to advance rapidly.

## Sources
- https://example.com/ai-2025
- https://example.com/llm-agents
"""
