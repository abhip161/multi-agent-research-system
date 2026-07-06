"""Pydantic models for structured data throughout the pipeline.

These models replace raw strings between pipeline stages, providing
validation, serialization, and clear contracts between components.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


# ── Search ────────────────────────────────────────────────────────────────────

class SearchResult(BaseModel):
    """A single search result from Tavily."""

    title: str
    url: str
    snippet: str

    def to_text(self) -> str:
        """Format as readable text for LLM consumption."""
        return f"Title: {self.title}\nURL: {self.url}\nSnippet: {self.snippet}"


class SearchResults(BaseModel):
    """Collection of search results with metadata."""

    query: str
    results: list[SearchResult] = Field(default_factory=list)
    searched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_text(self) -> str:
        """Format all results as readable text for LLM consumption."""
        if not self.results:
            return "No search results found."
        return "\n\n".join(r.to_text() for r in self.results)

    def get_urls(self) -> list[str]:
        """Extract all URLs from results."""
        return [r.url for r in self.results]


# ── Scraping ──────────────────────────────────────────────────────────────────

class ScrapedDocument(BaseModel):
    """Content scraped from a single URL."""

    url: str
    content: str
    char_count: int = 0
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and bool(self.content)

    def model_post_init(self, __context) -> None:
        """Auto-calculate char_count after init."""
        if self.char_count == 0 and self.content:
            self.char_count = len(self.content)


class ScrapedResults(BaseModel):
    """Collection of scraped documents from parallel scraping."""

    documents: list[ScrapedDocument] = Field(default_factory=list)

    @property
    def successful(self) -> list[ScrapedDocument]:
        return [d for d in self.documents if d.success]

    def to_text(self) -> str:
        """Merge all successful scraped content into a single string."""
        parts = []
        for doc in self.successful:
            parts.append(f"--- Content from: {doc.url} ---\n{doc.content}")
        return "\n\n".join(parts) if parts else "No content could be scraped."


# ── Report ────────────────────────────────────────────────────────────────────

class ResearchReport(BaseModel):
    """A complete research report produced by the writer chain."""

    topic: str
    content: str  # Full markdown content from the LLM
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_count: int = 0


# ── Critic ────────────────────────────────────────────────────────────────────

class CriticFeedback(BaseModel):
    """Feedback produced by the critic chain."""

    content: str  # Full text feedback from the LLM
    reviewed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Pipeline ──────────────────────────────────────────────────────────────────

class PipelineResult(BaseModel):
    """Complete output from a pipeline run — all stages + errors."""

    topic: str = ""
    search: Optional[SearchResults] = None
    scraped: Optional[ScrapedResults] = None
    report: Optional[ResearchReport] = None
    feedback: Optional[CriticFeedback] = None
    errors: list[str] = Field(default_factory=list)
    completed_steps: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None

    @property
    def success(self) -> bool:
        """True if all four steps completed without errors."""
        return len(self.errors) == 0 and len(self.completed_steps) == 4

    @property
    def duration_seconds(self) -> float | None:
        """Execution time in seconds, or None if not finished."""
        if self.finished_at and self.started_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

    def to_display_dict(self) -> dict[str, str]:
        """Return a dict keyed by step name for UI consumption."""
        d: dict[str, str] = {}
        if self.search:
            d["search"] = self.search.to_text()
        if self.scraped:
            d["reader"] = self.scraped.to_text()
        if self.report:
            d["writer"] = self.report.content
        if self.feedback:
            d["critic"] = self.feedback.content
        return d
