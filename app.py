"""ResearchMind — Streamlit UI for the multi-agent research pipeline.

This module is purely UI — all business logic lives in ``pipeline.py``.
CSS is loaded from ``static/style.css``.

Run with::

    streamlit run app.py
"""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

import streamlit as st

from export import export_markdown, export_pdf
from logger import setup_logging
from models import PipelineResult
from pipeline import ALL_STEPS, ResearchPipeline

# ── Initialize logging once at app startup ────────────────────────────────────
setup_logging()


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ResearchMind · AI Research Agent",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ── Load external CSS ────────────────────────────────────────────────────────
_css_path = Path(__file__).parent / "static" / "style.css"
if _css_path.exists():
    st.markdown(f"<style>{_css_path.read_text()}</style>", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe(text: str) -> str:
    """Escape HTML entities to prevent XSS in unsafe_allow_html blocks."""
    return html.escape(str(text))


def step_card(num: str, title: str, state: str, desc: str = "") -> None:
    """Render a pipeline step card with status indicator."""
    status_map = {
        "waiting": ("WAITING", "status-waiting"),
        "running": ("● RUNNING", "status-running"),
        "done":    ("✓ DONE",   "status-done"),
    }
    label, cls = status_map.get(state, ("", ""))
    card_cls = {"running": "active", "done": "done"}.get(state, "")

    desc_html = (
        f'<div style="font-size:0.82rem;color:#706860;margin-top:0.3rem;">'
        f'{_safe(desc)}</div>'
        if desc else ""
    )

    st.markdown(f"""
    <div class="step-card {card_cls}">
        <div class="step-header">
            <span class="step-num">{_safe(num)}</span>
            <span class="step-title">{_safe(title)}</span>
            <span class="step-status {cls}">{label}</span>
        </div>
        {desc_html}
    </div>
    """, unsafe_allow_html=True)


def get_step_state(step: str, results: dict, is_running: bool) -> str:
    """Determine the visual state (waiting/running/done) of a pipeline step."""
    if not results:
        return "waiting"
    if step in results:
        return "done"
    if is_running:
        for s in ALL_STEPS:
            if s not in results:
                return "running" if s == step else "waiting"
    return "waiting"


# ── Session state init ────────────────────────────────────────────────────────
if "results" not in st.session_state:
    st.session_state.results = {}
if "running" not in st.session_state:
    st.session_state.running = False
if "done" not in st.session_state:
    st.session_state.done = False
if "errors" not in st.session_state:
    st.session_state.errors = []
if "pipeline_result" not in st.session_state:
    st.session_state.pipeline_result = None


# ── Hero ──────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero">
    <div class="hero-eyebrow">Multi-Agent AI System</div>
    <h1>Research<span>Mind</span></h1>
    <p class="hero-sub">
        Four specialized AI agents collaborate — searching, scraping, writing,
        and critiquing — to deliver a polished research report on any topic.
    </p>
</div>
<div class="divider"></div>
""", unsafe_allow_html=True)


# ── Layout: input left, pipeline right ────────────────────────────────────────
col_input, col_spacer, col_pipeline = st.columns([5, 0.5, 4])

with col_input:
    st.markdown('<div class="input-card">', unsafe_allow_html=True)
    topic = st.text_input(
        "Research Topic",
        placeholder="e.g. Quantum computing breakthroughs in 2025",
        key="topic_input",
        label_visibility="visible",
        max_chars=500,
    )
    run_btn = st.button("⚡  Run Research Pipeline", use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # Example chips
    st.markdown("""
    <div style="display:flex;gap:0.5rem;flex-wrap:wrap;margin-bottom:1.5rem;">
        <span style="font-family:'DM Mono',monospace;font-size:0.68rem;
              color:#605850;letter-spacing:0.1em;">TRY →</span>
    """, unsafe_allow_html=True)
    for ex in ["LLM agents 2025", "CRISPR gene editing", "Fusion energy progress"]:
        st.markdown(f"""
        <span style="
            background:rgba(255,255,255,0.04);
            border:1px solid rgba(255,255,255,0.08);
            border-radius:6px;
            padding:0.25rem 0.7rem;
            font-size:0.75rem;
            color:#a09890;
            font-family:'DM Sans',sans-serif;
            cursor:default;
        ">{_safe(ex)}</span>
        """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

with col_pipeline:
    st.markdown('<div class="section-heading">Pipeline</div>', unsafe_allow_html=True)

    r = st.session_state.results
    is_running = st.session_state.running

    step_card("01", "Search Agent",  get_step_state("search", r, is_running), "Gathers recent web information")
    step_card("02", "Reader Agent",  get_step_state("reader", r, is_running), "Scrapes & extracts deep content")
    step_card("03", "Writer Chain",  get_step_state("writer", r, is_running), "Drafts the full research report")
    step_card("04", "Critic Chain",  get_step_state("critic", r, is_running), "Reviews & scores the report")


# ── Run pipeline ──────────────────────────────────────────────────────────────
if run_btn:
    if not topic or not topic.strip():
        st.warning("Please enter a research topic first.")
    else:
        st.session_state.results = {}
        st.session_state.errors = []
        st.session_state.pipeline_result = None
        st.session_state.running = True
        st.session_state.done = False
        st.rerun()

if st.session_state.running and not st.session_state.done:
    topic_val = st.session_state.topic_input

    def on_step_complete(step_name: str, _output: str) -> None:
        """Update session state as each step finishes (for UI)."""
        pass  # Pipeline runs synchronously; UI updates on rerun

    with st.spinner("🔬  ResearchMind is working…"):
        pipeline = ResearchPipeline(on_step_complete=on_step_complete)
        result = pipeline.run(topic_val)

    st.session_state.results = result.to_display_dict()
    st.session_state.errors = result.errors
    st.session_state.pipeline_result = result
    st.session_state.running = False
    st.session_state.done = True
    st.rerun()


# ── Error display ─────────────────────────────────────────────────────────────
if st.session_state.errors:
    for error in st.session_state.errors:
        st.markdown(f"""
        <div class="error-panel">
            <div class="error-panel-title">⚠ Pipeline Error</div>
            <div class="error-content">{_safe(error)}</div>
        </div>
        """, unsafe_allow_html=True)


# ── Results display ───────────────────────────────────────────────────────────
r = st.session_state.results

if r:
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-heading">Results</div>', unsafe_allow_html=True)

    # Raw outputs in expanders
    if "search" in r:
        with st.expander("🔍 Search Results (raw)", expanded=False):
            st.markdown(
                f'<div class="result-panel">'
                f'<div class="result-panel-title">Search Agent Output</div>'
                f'<div class="result-content">{_safe(r["search"])}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    if "reader" in r:
        with st.expander("📄 Scraped Content (raw)", expanded=False):
            st.markdown(
                f'<div class="result-panel">'
                f'<div class="result-panel-title">Reader Agent Output</div>'
                f'<div class="result-content">{_safe(r["reader"])}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # Final report — rendered as native markdown (Streamlit escapes it safely)
    if "writer" in r:
        st.markdown("""
        <div class="report-panel">
            <div class="panel-label orange">📝 Final Research Report</div>
        """, unsafe_allow_html=True)
        st.markdown(r["writer"])
        st.markdown("</div>", unsafe_allow_html=True)

        # ── Export buttons ────────────────────────────────────────────
        pipeline_result: PipelineResult | None = st.session_state.pipeline_result

        col_md, col_pdf = st.columns(2)

        with col_md:
            if pipeline_result and pipeline_result.report:
                md_content = export_markdown(pipeline_result)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                st.download_button(
                    label="⬇  Download Report (.md)",
                    data=md_content,
                    file_name=f"research_report_{timestamp}.md",
                    mime="text/markdown",
                    use_container_width=True,
                )

        with col_pdf:
            if pipeline_result and pipeline_result.report:
                try:
                    pdf_bytes = export_pdf(pipeline_result)
                    st.download_button(
                        label="⬇  Download Report (.pdf)",
                        data=pdf_bytes,
                        file_name=f"research_report_{timestamp}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )
                except Exception:
                    st.caption("PDF export requires `fpdf2`. Run: `uv add fpdf2`")

    # Critic feedback
    if "critic" in r:
        st.markdown("""
        <div class="feedback-panel">
            <div class="panel-label green">🧐 Critic Feedback</div>
        """, unsafe_allow_html=True)
        st.markdown(r["critic"])
        st.markdown("</div>", unsafe_allow_html=True)

    # Execution time
    pipeline_result = st.session_state.pipeline_result
    if pipeline_result and pipeline_result.duration_seconds:
        st.markdown(
            f'<div class="notice">Completed in {pipeline_result.duration_seconds:.1f}s</div>',
            unsafe_allow_html=True,
        )


# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="notice">
    ResearchMind · Powered by LangChain multi-agent pipeline · Built with Streamlit
</div>
""", unsafe_allow_html=True)