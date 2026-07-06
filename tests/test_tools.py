"""Tests for tools.py — URL validation, scraping, search (all mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests


class TestURLValidation:
    """Test the URL validation / SSRF prevention logic."""

    def test_valid_https_url(self):
        from tools import validate_url
        is_safe, reason = validate_url("https://example.com/article")
        assert is_safe is True
        assert reason == ""

    def test_valid_http_url(self):
        from tools import validate_url
        is_safe, reason = validate_url("http://example.com/page")
        assert is_safe is True

    def test_file_scheme_blocked(self):
        from tools import validate_url
        is_safe, reason = validate_url("file:///etc/passwd")
        assert is_safe is False
        assert "Scheme" in reason

    def test_ftp_scheme_blocked(self):
        from tools import validate_url
        is_safe, reason = validate_url("ftp://example.com/file")
        assert is_safe is False

    def test_localhost_blocked(self):
        from tools import validate_url
        is_safe, reason = validate_url("http://localhost:8080/admin")
        assert is_safe is False
        assert "blocked" in reason.lower()

    def test_127_0_0_1_blocked(self):
        from tools import validate_url
        is_safe, reason = validate_url("http://127.0.0.1/secret")
        assert is_safe is False

    def test_aws_metadata_blocked(self):
        from tools import validate_url
        is_safe, reason = validate_url("http://169.254.169.254/latest/meta-data/")
        assert is_safe is False

    def test_private_ip_10_blocked(self):
        from tools import validate_url
        is_safe, reason = validate_url("http://10.0.0.1/internal")
        assert is_safe is False

    def test_private_ip_192_blocked(self):
        from tools import validate_url
        is_safe, reason = validate_url("http://192.168.1.1/router")
        assert is_safe is False

    def test_empty_url(self):
        from tools import validate_url
        is_safe, reason = validate_url("")
        assert is_safe is False

    def test_malformed_url(self):
        from tools import validate_url
        is_safe, reason = validate_url("not-a-url")
        assert is_safe is False


class TestCleanHTML:
    """Test HTML cleaning and text extraction."""

    def test_removes_scripts(self, sample_html):
        from tools import _clean_html
        text = _clean_html(sample_html, 5000)
        assert "alert" not in text
        assert "xss" not in text

    def test_removes_style(self, sample_html):
        from tools import _clean_html
        text = _clean_html(sample_html, 5000)
        assert "display: none" not in text

    def test_removes_nav(self, sample_html):
        from tools import _clean_html
        text = _clean_html(sample_html, 5000)
        assert "Menu" not in text

    def test_preserves_content(self, sample_html):
        from tools import _clean_html
        text = _clean_html(sample_html, 5000)
        assert "Research Article" in text
        assert "main content" in text

    def test_truncation_at_word_boundary(self):
        from tools import _clean_html
        html = "<p>word1 word2 word3 word4 word5</p>"
        text = _clean_html(html, 15)
        # Should truncate at a word boundary, not mid-word
        assert text.endswith("…") or len(text) <= 15

    def test_empty_html(self):
        from tools import _clean_html
        text = _clean_html("<html><body></body></html>", 1000)
        assert text == ""


class TestWebSearch:
    """Test web_search tool with mocked Tavily API."""

    @patch("tools._tavily")
    def test_successful_search(self, mock_tavily, sample_tavily_response):
        mock_tavily.search.return_value = sample_tavily_response

        from tools import web_search
        result = web_search.invoke("AI breakthroughs 2025")

        assert "AI Breakthroughs" in result
        assert "https://example.com/ai-2025" in result
        mock_tavily.search.assert_called_once()

    @patch("tools._tavily")
    def test_empty_results(self, mock_tavily):
        mock_tavily.search.return_value = {"results": []}

        from tools import web_search
        result = web_search.invoke("obscure query with no results")

        assert "No results found" in result

    @patch("tools._tavily")
    def test_api_error_handled(self, mock_tavily):
        mock_tavily.search.side_effect = Exception("API rate limit exceeded")

        from tools import web_search
        with pytest.raises(Exception):
            web_search.invoke("test query")


class TestScrapeUrl:
    """Test scrape_url tool with mocked HTTP requests."""

    @patch("tools._scrape_single_url")
    def test_successful_scrape(self, mock_scrape):
        mock_scrape.return_value = "Extracted article content about AI research."

        from tools import scrape_url
        result = scrape_url.invoke("https://example.com/article")

        assert "Extracted article content" in result

    def test_unsafe_url_rejected(self):
        from tools import scrape_url
        result = scrape_url.invoke("file:///etc/passwd")
        assert "Error" in result
        assert "Cannot scrape" in result

    def test_localhost_rejected(self):
        from tools import scrape_url
        result = scrape_url.invoke("http://localhost:3000/admin")
        assert "Error" in result
