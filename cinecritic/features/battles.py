"""Head-to-Head Movie Battles: resolve two films, reuse or create analyses, compare, explain."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

from .. import scoring, spoilers
from ..ai.gateway import Gateway
from ..config import DIMENSIONS, PROMPT_VERSION
from ..errors import AppError, ErrorCategory, InvalidInputError
from ..metadata import choose_candidate, parse_title_year, search_movies
from ..pipeline import PipelineRun, call_with_retries, stage_scope
from ..prompts import compare_system
from ..services import Analysis, analyze_movie, facts_text, sanitize_query, to_text
from .serialize import analysis_from_dict, analysis_key, analysis_to_dict


@dataclass(frozen=True)
class BattleResult:
    a: Analysis
    b: Analysis
    comparison: scoring.Comparison
    narrative: str = ""
    notices: tuple[str, ...] = ()
    run: PipelineRun | None = None


def _resolve(query: str, tmdb_key: str, secrets: list[str]) -> tuple[str, str]:
    """(display query, film key) using TMDB when available so identity is a real ID."""
    query = sanitize_query(query)
    if not tmdb_key:
        return query, ""
    title, year = parse_title_year(query)
    cands = call_with_retries(lambda: search_movies(title, tmdb_key, year), stage="resolve", source="tmdb",
                              secrets=secrets, max_attempts=2)
    sel = choose_candidate(cands, title, year)
    if sel is None:
        raise AppError(ErrorCategory.TMDB, f"TMDB has no match for “{title}”.", stage="resolve", source="tmdb")
    best = sel.best
    return f"{best.title} ({best.year})" if best.year else best.title, f"tmdb:{best.id}"


def narrative_input(a: Analysis, b: Analysis, comp: scoring.Comparison) -> str:
    def block(tag: str, x: Analysis) -> str:
        c = x.critique
        scores = scoring.dimension_scores(c)
        rows = "\n".join(f"  - {t}: {scores[k]:.1f}/10 — {getattr(c, k).summary}" for k, t in DIMENSIONS
                         if scores[k] is not None)
        facts = facts_text(x.meta).strip()
        return (f"FILM {tag}: {c.title} ({c.year})\n{facts}\n  Verdict: {c.verdict_label}. {c.verdict_text}\n"
                f"  Strengths: {'; '.join(c.strengths)}\n  Weaknesses: {'; '.join(c.flaws)}\n{rows}")

    outcomes = ", ".join(f"{scoring.label(r.key)}: {r.outcome}" for r in comp.dims)
    return f"{block('A', a)}\n\n{block('B', b)}\n\nSCORE COMPARISON (A vs B): {outcomes}\nLeader by rule: {comp.leader}"


def run_battle(
    gateway: Gateway,
    query_a: str,
    query_b: str,
    *,
    run: PipelineRun,
    tmdb_key: str = "",
    secrets: list[str] | None = None,
    weights: dict[str, float] | None = None,
    level: str = "none",
    depth: str = "standard",
    language: str = "English",
    load: Callable[[str, str], Analysis | None] = lambda key, level: None,
    save: Callable[[Analysis], None] = lambda a: None,
    sub_run_factory: Callable[[str], PipelineRun] | None = None,
) -> BattleResult:
    """Observable battle pipeline. Raises AppError only if the two analyses cannot be obtained.

    The AI write-up is optional: if it fails, the deterministic score comparison is still returned.
    """
    secrets = [s for s in (*(secrets or []), tmdb_key) if s]
    level = spoilers.effective_level(level)
    notices: list[str] = []
    fail_rest = ("data", "init", "compare", "narrative")

    # 1. resolve identities
    try:
        with stage_scope(run, "resolve"):
            qa, ka = _resolve(query_a, tmdb_key, secrets)
            qb, kb = _resolve(query_b, tmdb_key, secrets)
            if (ka and ka == kb) or qa.lower() == qb.lower():
                raise InvalidInputError("Pick two different films to compare.", stage="resolve")
            run.complete("resolve", note=f"A: {qa}  |  B: {qb}" + ("" if tmdb_key else "  (title match only; no TMDB key)"))
    except AppError:
        for sid in fail_rest:
            run.skip(sid, "Skipped: films could not be resolved")
        run.finish()
        raise

    # 2. gather analyses (stored ones are reused; missing ones run the normal critique pipeline)
    def obtain(query: str, key: str) -> Analysis:
        stored = load(key, level) if key else None
        if stored is not None:
            run.event("data", "info", f"reused stored analysis for {query}")
            return stored
        sub = sub_run_factory(query) if sub_run_factory else PipelineRun(query, gateway.label("analysis"))
        result = analyze_movie(gateway, query, run=sub, tmdb_key=tmdb_key, n_recs=0, secrets=secrets,
                               spoiler_level=level, depth=depth, language=language)
        if not result.critique.recognized:
            raise AppError(ErrorCategory.INVALID_INPUT, f"“{query}” was not recognised as a released film.",
                           stage="data")
        save(result)
        return result

    try:
        with stage_scope(run, "data"):
            with ThreadPoolExecutor(max_workers=2) as pool:
                fa, fb = pool.submit(obtain, qa, ka), pool.submit(obtain, qb, kb)
                a, b = fa.result(), fb.result()
            run.complete("data", note=f"{a.critique.title} and {b.critique.title} ready", cached=a.from_storage and b.from_storage)
    except AppError:
        for sid in fail_rest[1:]:
            run.skip(sid, "Skipped: analyses unavailable")
        run.finish()
        raise

    # 3. AI setup for the optional write-up (failure only removes the write-up)
    init_ok = True
    try:
        with stage_scope(run, "init"):
            ref = gateway.prepare("summarize", run, "init")
            run.complete("init", note=f"{ref} ready")
    except AppError as err:
        init_ok = False
        notices.append(f"The written comparison is unavailable: {err.message}")

    # 4. deterministic comparison
    with stage_scope(run, "compare"):
        comp = scoring.compare_scores(scoring.dimension_scores(a.critique), scoring.dimension_scores(b.critique), weights)
        missing = [scoring.label(r.key) for r in comp.dims if r.outcome == "insufficient"]
        if missing:
            notices.append("Not enough evidence to compare: " + ", ".join(missing) + ".")
        run.complete("compare", note=f"{comp.decided} comparable categories; result: {comp.leader.replace('_', ' ')}")

    # 5. AI write-up
    narrative = ""
    if not init_ok:
        run.skip("narrative", "Skipped: AI model unavailable")
    else:
        try:
            with stage_scope(run, "narrative"):
                data = narrative_input(a, b, comp)

                def write(llm, cfg):
                    from langchain_core.messages import HumanMessage, SystemMessage
                    return to_text(llm.invoke([SystemMessage(content=compare_system(level)), HumanMessage(content=data)],
                                              config=cfg).content)

                narrative = gateway.call("summarize", write, run=run, stage="narrative", secrets=secrets,
                                         validate=lambda t: (_ for _ in ()).throw(AppError(
                                             ErrorCategory.MALFORMED, "Empty comparison.", retryable=True, source="ai"))
                                         if not t.strip() else None).strip()
                if level != "full":
                    narrative, removed = spoilers.clean_text(narrative, "light")
                    if removed:
                        notices.append(f"{removed} sentence(s) were removed from the write-up to protect spoilers.")
                run.complete("narrative", note=f"Written by {gateway.model_used('summarize')}")
        except AppError as err:
            notices.append(f"The written comparison is unavailable: {err.message}")
    run.finish()
    return BattleResult(a, b, comp, narrative, tuple(notices), run)
