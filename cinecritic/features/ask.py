"""Ask the Critic: a contextual film chat built on the AI gateway."""
from __future__ import annotations

import re

from .. import scoring, spoilers
from ..ai.gateway import Gateway
from ..config import DIMENSIONS
from ..errors import AppError, ErrorCategory, InvalidInputError
from ..pipeline import PipelineRun, stage_scope
from ..prompts import ask_messages, ask_system
from ..services import Analysis, facts_text, to_text

MAX_QUESTION = 800
HISTORY_TURNS = 8          # most recent messages sent to the model
MAX_ARCHIVE_IN_CONTEXT = 25


def sanitize_question(text: str) -> str:
    cleaned = re.sub(r"[ \t]+", " ", text or "").strip()[:MAX_QUESTION]
    if not cleaned:
        raise InvalidInputError("Type a question first.", stage="input")
    return cleaned


def film_context(a: Analysis | None, level: str = "none") -> str:
    """Verified TMDB facts + CineCritic's existing analysis, so the full critique is never re-run."""
    if a is None:
        return ""
    c = a.critique
    lines = [f"FILM: {c.title or a.query} ({c.year})"]
    facts = facts_text(a.meta).strip()
    if facts:
        lines.append(facts + "  [verified by TMDB]")
    scores = scoring.dimension_scores(c)
    rows = [f"- {title}: {scores[key]:.1f}/10 — {getattr(c, key).summary}" for key, title in DIMENSIONS
            if scores[key] is not None]
    lines.append("CINECRITIC ANALYSIS (AI opinion, not fact):")
    lines += rows
    if c.verdict_label:
        lines.append(f"- Verdict: {c.verdict_label}. {c.verdict_text}")
    if c.strengths:
        lines.append("- Strengths: " + "; ".join(c.strengths))
    if c.flaws:
        lines.append("- Weaknesses: " + "; ".join(c.flaws))
    if level in ("light", "full") and c.spoiler_notes:
        lines.append(f"- Spoiler notes ({level}): {c.spoiler_notes}")
    return "\n".join(lines)


def archive_context(entries: list[dict]) -> str:
    """The user's saved collection (only sent when they enable it)."""
    if not entries:
        return ""
    rows = []
    for e in entries[:MAX_ARCHIVE_IN_CONTEXT]:
        rating = f", rated {e['rating']:.1f}/10" if e.get("rating") is not None else ""
        fav = ", favourite" if e.get("favorite") else ""
        rows.append(f"- {e['title']} ({e.get('year') or '?'}): {e['status']}{rating}{fav}")
    return "USER'S SAVED FILMS (shared with permission):\n" + "\n".join(rows)


def ask_critic(gateway: Gateway, question: str, history: list[tuple[str, str]], *, context: str, level: str,
               length: str, language: str, run: PipelineRun, secrets=()) -> tuple[str, int]:
    """Answer one question. Returns (answer, spoiler_sentences_removed)."""
    try:
        with stage_scope(run, "input"):
            question = sanitize_question(question)
            run.complete("input", note=f"{len(question)} characters")
    except AppError:
        for sid in ("context", "init", "answer"):
            run.skip(sid, "Skipped: invalid input")
        run.finish()
        raise
    with stage_scope(run, "context"):
        trimmed = [(r, t[:1500]) for r, t in history[-HISTORY_TURNS:]]
        run.complete("context", note=f"{len(context)} characters of context, {len(trimmed)} earlier messages")
    try:
        with stage_scope(run, "init"):
            ref = gateway.prepare("ask", run, "init")
            run.complete("init", note=f"{ref} ready")
    except AppError:
        run.skip("answer", "Skipped: AI model unavailable")
        run.finish()
        raise
    level = spoilers.effective_level(level)
    messages = ask_messages(ask_system(level, length, language), context, trimmed, question)

    def check(text: str) -> None:
        if not text.strip():
            raise AppError(ErrorCategory.MALFORMED, "The model returned an empty answer. Please try again.",
                           retryable=True, source="ai")

    try:
        with stage_scope(run, "answer"):
            answer = gateway.call("ask", lambda llm, cfg: to_text(llm.invoke(messages, config=cfg).content),
                                  run=run, stage="answer", secrets=secrets, validate=check)
            removed = 0
            if level != "full":
                answer, removed = spoilers.clean_text(answer, "light")
            run.complete("answer", note=f"Answer from {gateway.model_used('ask')}")
    except AppError:
        run.finish()
        raise
    run.finish()
    return answer.strip(), removed
