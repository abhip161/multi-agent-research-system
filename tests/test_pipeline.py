"""Tests for pipeline.py — pipeline orchestration with mocked agents."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestExtractUrls:
    """Test URL extraction from text."""

    def test_extracts_https(self):
        from pipeline import _extract_urls
        urls = _extract_urls("Visit https://example.com/page for more info")
        assert "https://example.com/page" in urls

    def test_extracts_http(self):
        from pipeline import _extract_urls
        urls = _extract_urls("See http://test.org/article")
        assert "http://test.org/article" in urls

    def test_extracts_multiple(self):
        from pipeline import _extract_urls
        text = "URL1: https://a.com URL2: https://b.com/path"
        urls = _extract_urls(text)
        assert len(urls) == 2

    def test_no_urls(self):
        from pipeline import _extract_urls
        urls = _extract_urls("No URLs in this text at all")
        assert urls == []


class TestResearchPipeline:
    """Test ResearchPipeline with mocked agents and chains."""

    def test_empty_topic_returns_error(self):
        from pipeline import ResearchPipeline
        pipeline = ResearchPipeline()
        result = pipeline.run("")
        assert not result.success
        assert "empty" in result.errors[0].lower()

    def test_whitespace_topic_returns_error(self):
        from pipeline import ResearchPipeline
        pipeline = ResearchPipeline()
        result = pipeline.run("   ")
        assert not result.success

    @patch("pipeline.build_search_agent")
    @patch("pipeline.scrape_urls_parallel")
    @patch("pipeline.writer_chain")
    @patch("pipeline.critic_chain")
    def test_full_pipeline_success(
        self, mock_critic, mock_writer, mock_scrape, mock_search
    ):
        """End-to-end pipeline with all mocked stages."""
        # Mock search agent
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {
            "messages": [MagicMock(content="Title: AI News\nURL: https://example.com/ai\nSnippet: Latest AI")]
        }
        mock_search.return_value = mock_agent

        # Mock parallel scrape
        from models import ScrapedDocument, ScrapedResults
        mock_scrape.return_value = ScrapedResults(documents=[
            ScrapedDocument(url="https://example.com/ai", content="Detailed AI content here")
        ])

        # Mock writer
        mock_writer.invoke.return_value = "## Introduction\nAI Report content"

        # Mock critic
        mock_critic.invoke.return_value = "**Score: 7/10**\nGood report."

        from pipeline import ResearchPipeline
        pipeline = ResearchPipeline()
        result = pipeline.run("AI breakthroughs")

        assert result.report is not None
        assert "AI Report" in result.report.content
        assert result.feedback is not None
        assert "7/10" in result.feedback.content
        assert len(result.completed_steps) == 4

    @patch("pipeline.build_search_agent")
    def test_search_failure_stops_pipeline(self, mock_search):
        """If search fails, pipeline should return with error."""
        mock_search.side_effect = Exception("API down")

        from pipeline import ResearchPipeline
        pipeline = ResearchPipeline()
        result = pipeline.run("test topic")

        assert not result.success
        assert any("Search failed" in e for e in result.errors)
        assert len(result.completed_steps) == 0

    def test_callback_invoked(self):
        """Step callback should be called for each completed step."""
        completed = []

        def callback(step, output):
            completed.append(step)

        with patch("pipeline.build_search_agent") as mock_search, \
             patch("pipeline.scrape_urls_parallel") as mock_scrape, \
             patch("pipeline.writer_chain") as mock_writer, \
             patch("pipeline.critic_chain") as mock_critic:

            mock_agent = MagicMock()
            mock_agent.invoke.return_value = {
                "messages": [MagicMock(content="URL: https://example.com")]
            }
            mock_search.return_value = mock_agent

            from models import ScrapedDocument, ScrapedResults
            mock_scrape.return_value = ScrapedResults(documents=[
                ScrapedDocument(url="https://example.com", content="Content")
            ])
            mock_writer.invoke.return_value = "Report"
            mock_critic.invoke.return_value = "Score: 8/10"

            from pipeline import ResearchPipeline
            pipeline = ResearchPipeline(on_step_complete=callback)
            pipeline.run("test topic")

        assert len(completed) == 4
