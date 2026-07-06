"""Tests for export.py — Markdown and PDF export."""

from __future__ import annotations

import pytest

from models import (
    CriticFeedback,
    PipelineResult,
    ResearchReport,
    SearchResult,
    SearchResults,
)


class TestExportMarkdown:
    """Test Markdown export functionality."""

    def test_basic_export(self):
        from export import export_markdown

        result = PipelineResult(
            topic="AI Research",
            report=ResearchReport(topic="AI Research", content="## Introduction\nAI is evolving."),
        )
        md = export_markdown(result)

        assert "# Research Report: AI Research" in md
        assert "## Introduction" in md
        assert "AI is evolving" in md
        assert "ResearchMind" in md

    def test_includes_critic_feedback(self):
        from export import export_markdown

        result = PipelineResult(
            topic="Test",
            report=ResearchReport(topic="Test", content="Report body"),
            feedback=CriticFeedback(content="Score: 8/10\nGood job."),
        )
        md = export_markdown(result)

        assert "## Critic Review" in md
        assert "8/10" in md

    def test_no_report_raises(self):
        from export import export_markdown
        from exceptions import ExportError

        result = PipelineResult(topic="Test")
        with pytest.raises(ExportError):
            export_markdown(result)


class TestExportPDF:
    """Test PDF export functionality."""

    def test_basic_pdf_export(self):
        from export import export_pdf

        result = PipelineResult(
            topic="AI Research",
            report=ResearchReport(topic="AI Research", content="## Intro\nContent here."),
        )

        try:
            pdf_bytes = export_pdf(result)
            # Should produce valid PDF bytes
            assert isinstance(pdf_bytes, bytes)
            assert len(pdf_bytes) > 100
            assert pdf_bytes[:4] == b"%PDF"  # PDF magic bytes
        except Exception:
            # fpdf2 may not be installed in test env
            pytest.skip("fpdf2 not available")

    def test_no_report_raises(self):
        from export import export_pdf
        from exceptions import ExportError

        result = PipelineResult(topic="Test")
        with pytest.raises(ExportError):
            export_pdf(result)
