"""Tests for models.py — Pydantic model validation."""

from __future__ import annotations

import pytest

from models import (
    CriticFeedback,
    PipelineResult,
    ResearchReport,
    ScrapedDocument,
    ScrapedResults,
    SearchResult,
    SearchResults,
)


class TestSearchResult:
    """Test SearchResult model."""

    def test_to_text(self):
        r = SearchResult(title="Test", url="https://example.com", snippet="Content")
        text = r.to_text()
        assert "Test" in text
        assert "https://example.com" in text
        assert "Content" in text


class TestSearchResults:
    """Test SearchResults collection."""

    def test_to_text_with_results(self):
        results = SearchResults(
            query="test",
            results=[
                SearchResult(title="A", url="https://a.com", snippet="Snippet A"),
                SearchResult(title="B", url="https://b.com", snippet="Snippet B"),
            ],
        )
        text = results.to_text()
        assert "https://a.com" in text
        assert "https://b.com" in text

    def test_to_text_empty(self):
        results = SearchResults(query="test", results=[])
        assert "No search results" in results.to_text()

    def test_get_urls(self):
        results = SearchResults(
            query="test",
            results=[
                SearchResult(title="A", url="https://a.com", snippet=""),
                SearchResult(title="B", url="https://b.com", snippet=""),
            ],
        )
        assert results.get_urls() == ["https://a.com", "https://b.com"]


class TestScrapedDocument:
    """Test ScrapedDocument model."""

    def test_success_property(self):
        doc = ScrapedDocument(url="https://a.com", content="Content here")
        assert doc.success is True

    def test_failure_property(self):
        doc = ScrapedDocument(url="https://a.com", content="", error="Timeout")
        assert doc.success is False

    def test_char_count_auto(self):
        doc = ScrapedDocument(url="https://a.com", content="Hello world")
        assert doc.char_count == 11


class TestScrapedResults:
    """Test ScrapedResults collection."""

    def test_successful_filter(self):
        results = ScrapedResults(documents=[
            ScrapedDocument(url="https://a.com", content="Good content"),
            ScrapedDocument(url="https://b.com", content="", error="Failed"),
            ScrapedDocument(url="https://c.com", content="More content"),
        ])
        assert len(results.successful) == 2

    def test_to_text(self):
        results = ScrapedResults(documents=[
            ScrapedDocument(url="https://a.com", content="Content A"),
        ])
        text = results.to_text()
        assert "Content A" in text
        assert "https://a.com" in text


class TestPipelineResult:
    """Test PipelineResult model."""

    def test_success_when_all_steps_done(self):
        result = PipelineResult(
            topic="test",
            completed_steps=["search", "reader", "writer", "critic"],
        )
        assert result.success is True

    def test_not_success_with_errors(self):
        result = PipelineResult(
            topic="test",
            completed_steps=["search", "reader", "writer", "critic"],
            errors=["Something failed"],
        )
        assert result.success is False

    def test_not_success_incomplete(self):
        result = PipelineResult(
            topic="test",
            completed_steps=["search", "reader"],
        )
        assert result.success is False

    def test_to_display_dict(self):
        result = PipelineResult(
            topic="test",
            search=SearchResults(query="test", results=[
                SearchResult(title="A", url="https://a.com", snippet="S"),
            ]),
            report=ResearchReport(topic="test", content="Report text"),
        )
        d = result.to_display_dict()
        assert "search" in d
        assert "writer" in d
        assert "Report text" in d["writer"]
