"""Research pipeline orchestration — single source of truth.

Provides ``ResearchPipeline`` which executes the four-stage multi-agent
workflow. Used by both the Streamlit UI (``app.py``) and CLI.

The pipeline:
    1. **Search** — Tavily web search via LangChain agent
    2. **Reader** — Parallel URL scraping (aiohttp) for top results
    3. **Writer** — LLM chain drafts a structured research report
    4. **Critic** — LLM chain reviews and scores the report

All stages are wrapped in error handling. Partial results are preserved
even if later stages fail.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Callable

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from agents import build_reader_agent, build_search_agent, critic_chain, writer_chain
from config import settings
from exceptions import CriticError, ScrapeError, SearchError, WriterError
from logger import get_logger
from models import (
    CriticFeedback,
    PipelineResult,
    ResearchReport,
    ScrapedResults,
    SearchResult,
    SearchResults,
)
from tools import scrape_urls_parallel

logger = get_logger(__name__)

# Step name constants — used as keys throughout the pipeline
STEP_SEARCH = "search"
STEP_READER = "reader"
STEP_WRITER = "writer"
STEP_CRITIC = "critic"
ALL_STEPS = (STEP_SEARCH, STEP_READER, STEP_WRITER, STEP_CRITIC)

# Type alias for step callbacks: (step_name, step_output) -> None
StepCallback = Callable[[str, str], None]


def _extract_urls(text: str) -> list[str]:
    """Extract HTTP(S) URLs from text using regex."""
    pattern = r"https?://[^\s<>\"')\]]*"
    return re.findall(pattern, text)


class ResearchPipeline:
    """Orchestrates the multi-agent research pipeline.

    Args:
        on_step_complete: Optional callback invoked after each step completes.
            Receives ``(step_name, step_output_text)``.
            Useful for UI progress updates.
    """

    def __init__(self, on_step_complete: StepCallback | None = None) -> None:
        self._on_step_complete = on_step_complete or (lambda _n, _o: None)

    def _notify(self, step: str, output: str) -> None:
        """Safely invoke the step callback."""
        try:
            self._on_step_complete(step, output)
        except Exception:
            logger.warning("Step callback failed for '%s'", step, exc_info=True)

    def run(self, topic: str) -> PipelineResult:
        """Execute the full research pipeline for the given topic.

        Returns a ``PipelineResult`` with all outputs and any errors.
        Partial results are preserved even if a later step fails.

        Args:
            topic: The research topic to investigate.
        """
        if not topic or not topic.strip():
            return PipelineResult(errors=["Topic cannot be empty."])

        topic = topic.strip()
        result = PipelineResult(topic=topic)
        pipeline_start = time.time()

        logger.info("═" * 60)
        logger.info("Pipeline started for topic: '%s'", topic)

        # ── Step 1: Search ────────────────────────────────────────────
        try:
            result = self._step_search(topic, result)
        except Exception as e:
            logger.exception("Search step failed fatally")
            result.errors.append(f"Search failed: {e}")
            result.finished_at = datetime.now(timezone.utc)
            return result  # Can't continue without search results

        # ── Step 2: Reader (parallel scrape) ──────────────────────────
        try:
            result = self._step_reader(topic, result)
        except Exception as e:
            logger.exception("Reader step failed fatally")
            result.errors.append(f"Reader failed: {e}")
            # Continue — writer can work with search results alone

        # ── Step 3: Writer ────────────────────────────────────────────
        try:
            result = self._step_writer(topic, result)
        except Exception as e:
            logger.exception("Writer step failed fatally")
            result.errors.append(f"Writer failed: {e}")
            result.finished_at = datetime.now(timezone.utc)
            return result  # Can't critique without a report

        # ── Step 4: Critic ────────────────────────────────────────────
        try:
            result = self._step_critic(result)
        except Exception as e:
            logger.exception("Critic step failed fatally")
            result.errors.append(f"Critic failed: {e}")
            # Report is still available without critique

        elapsed = time.time() - pipeline_start
        result.finished_at = datetime.now(timezone.utc)
        logger.info(
            "Pipeline finished in %.1fs — %d/%d steps completed, %d errors",
            elapsed, len(result.completed_steps), len(ALL_STEPS), len(result.errors),
        )
        logger.info("═" * 60)

        return result

    # ── Individual steps ──────────────────────────────────────────────────

    def _step_search(self, topic: str, result: PipelineResult) -> PipelineResult:
        """Step 1: Use search agent to find web information."""
        logger.info("Step 1/4: Searching for '%s'", topic)
        start = time.time()

        search_agent = build_search_agent()
        sr = search_agent.invoke({
            "messages": [
                ("user", f"Find recent, reliable and detailed information about: {topic}")
            ]
        })

        raw_text = sr["messages"][-1].content
        elapsed = time.time() - start

        # Parse URLs from the raw text to build structured results
        urls = _extract_urls(raw_text)
        result.search = SearchResults(
            query=topic,
            results=[
                SearchResult(title="", url=url, snippet="")
                for url in urls
            ],
        )

        result.completed_steps.append(STEP_SEARCH)
        self._notify(STEP_SEARCH, raw_text)
        logger.info("Search complete — %d chars, %d URLs in %.1fs", len(raw_text), len(urls), elapsed)
        # Store raw text for backwards compat with display_dict
        result.search._raw_text = raw_text  # type: ignore[attr-defined]
        return result

    def _step_reader(self, topic: str, result: PipelineResult) -> PipelineResult:
        """Step 2: Scrape top URLs from search results in parallel."""
        logger.info("Step 2/4: Scraping top resources")
        start = time.time()

        if not result.search or not result.search.get_urls():
            # Fallback: use the agent-based single scrape
            logger.warning("No URLs found in search results, using agent fallback")
            reader_agent = build_reader_agent()
            raw_text = getattr(result.search, "_raw_text", "") if result.search else ""
            rr = reader_agent.invoke({
                "messages": [
                    ("user",
                     f"Based on the following search results about '{topic}', "
                     f"pick the most relevant URL and scrape it for deeper content.\n\n"
                     f"Search Results:\n{raw_text[:settings.search_context_max_chars]}")
                ]
            })
            content = rr["messages"][-1].content
            from models import ScrapedDocument
            result.scraped = ScrapedResults(
                documents=[ScrapedDocument(url="agent-selected", content=content)]
            )
        else:
            # Parallel scrape top N URLs
            urls = result.search.get_urls()
            result.scraped = scrape_urls_parallel(urls)

        elapsed = time.time() - start
        success_count = len(result.scraped.successful) if result.scraped else 0
        result.completed_steps.append(STEP_READER)
        self._notify(STEP_READER, result.scraped.to_text() if result.scraped else "")
        logger.info("Scraping complete — %d successful in %.1fs", success_count, elapsed)
        return result

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=True,
    )
    def _invoke_writer(self, topic: str, research: str) -> str:
        """Invoke writer chain with retry on transient failures."""
        return writer_chain.invoke({"topic": topic, "research": research})

    def _step_writer(self, topic: str, result: PipelineResult) -> PipelineResult:
        """Step 3: Draft the research report."""
        logger.info("Step 3/4: Drafting report")
        start = time.time()

        # Combine search + scraped content
        search_text = getattr(result.search, "_raw_text", "") if result.search else ""
        if not search_text and result.search:
            search_text = result.search.to_text()

        research_combined = f"SEARCH RESULTS:\n{search_text}"
        if result.scraped and result.scraped.successful:
            research_combined += f"\n\nDETAILED SCRAPED CONTENT:\n{result.scraped.to_text()}"

        report_text = self._invoke_writer(topic, research_combined)

        elapsed = time.time() - start
        result.report = ResearchReport(
            topic=topic,
            content=report_text,
            source_count=len(result.search.get_urls()) if result.search else 0,
        )

        result.completed_steps.append(STEP_WRITER)
        self._notify(STEP_WRITER, report_text)
        logger.info("Report drafted — %d chars in %.1fs", len(report_text), elapsed)
        return result

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=True,
    )
    def _invoke_critic(self, report: str) -> str:
        """Invoke critic chain with retry on transient failures."""
        return critic_chain.invoke({"report": report})

    def _step_critic(self, result: PipelineResult) -> PipelineResult:
        """Step 4: Review and score the report."""
        logger.info("Step 4/4: Reviewing report")
        start = time.time()

        if not result.report:
            raise CriticError("No report to critique")

        feedback_text = self._invoke_critic(result.report.content)

        elapsed = time.time() - start
        result.feedback = CriticFeedback(content=feedback_text)

        result.completed_steps.append(STEP_CRITIC)
        self._notify(STEP_CRITIC, feedback_text)
        logger.info("Critique complete in %.1fs", elapsed)
        return result


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    from rich.console import Console
    from rich.panel import Panel

    console = Console()

    topic = console.input("\n[bold]Enter a research topic:[/bold] ").strip()
    if not topic:
        console.print("[red]Topic cannot be empty.[/red]")
        raise SystemExit(1)

    def cli_callback(step: str, _output: str) -> None:
        console.print(f"  [green]✓[/green] {step} complete")

    console.print(f"\n[bold]Researching:[/bold] {topic}\n")

    pipeline = ResearchPipeline(on_step_complete=cli_callback)
    result = pipeline.run(topic)

    if result.errors:
        for error in result.errors:
            console.print(f"[red]⚠ {error}[/red]")

    if result.report:
        console.print(Panel(result.report.content, title="Research Report", border_style="bright_blue"))

    if result.feedback:
        console.print(Panel(result.feedback.content, title="Critic Feedback", border_style="green"))

    if result.duration_seconds:
        console.print(f"\n[dim]Completed in {result.duration_seconds:.1f}s[/dim]")