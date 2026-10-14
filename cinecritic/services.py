"""Business logic: reviews, structured critiques and recommendations (UI-independent)."""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

from . import spoilers
from .ai.gateway import Gateway
from .cache import TTLCache
from .config import (
    ANALYSIS_CACHE_MAX,
    ANALYSIS_CACHE_TTL_S,
    MAX_QUERY_CHARS,
    MAX_WORDS,
    NUM_SIMILAR,
    PROMPT_VERSION,
)
from .errors import AppError, CritiqueError, ErrorCategory, InvalidInputError
from .metadata import (
    Candidate,
    MovieMeta,
    choose_candidate,
    fetch_details,
    fetch_recommendations,
    normalize_title,
    parse_title_year,
    search_movies,
)
from .pipeline import PipelineRun, call_with_retries, stage_scope
from .prompts import (
    CRITIQUE_TEMPLATE, EXTRACT_TEMPLATE, RECOMMEND_TEMPLATE, REVIEW_TEMPLATE, SEARCH_ASSIST_TEMPLATE, directives,
)
from .schemas import Critique, Movie, Recommendations, SearchFilters

CRITIQUE_CACHE = TTLCache(ANALYSIS_CACHE_TTL_S, ANALYSIS_CACHE_MAX)
RECOS_CACHE = TTLCache(ANALYSIS_CACHE_TTL_S, ANALYSIS_CACHE_MAX)


# --------------------------------------------------------------------------- text helpers
def to_text(content) -> str:
    """Normalize a model response: Mistral returns str, Gemini a list of blocks."""
    if isinstance(content, str):
        return content
    return "\n".join(
        block["text"] if isinstance(block, dict) else str(block)
        for block in content
        if not isinstance(block, dict) or "text" in block
    )


def to_bullets(text: str, max_words: int = MAX_WORDS) -> list[str]:
    """Split text into bullets and hard-cap the total word count."""
    lines = [
        re.sub(r"^\s*[-•*\d.)]+\s*", "", line).replace("**", "").strip()
        for line in text.splitlines()
        if line.strip()
    ]
    bullets: list[str] = []
    used = 0
    for line in lines:
        words = line.split()
        if used + len(words) > max_words:
            left = max_words - used
            if left >= 3:
                bullets.append(" ".join(words[:left]).rstrip(",;:") + "…")
            break
        bullets.append(line)
        used += len(words)
    return bullets


def sanitize_query(text: str) -> str:
    """Collapse whitespace and cap length. Raises ValueError for empty input."""
    cleaned = re.sub(r"\s+", " ", text or "").strip()[:MAX_QUERY_CHARS]
    if not cleaned:
        raise InvalidInputError("Enter a movie name first.")
    return cleaned


# --------------------------------------------------------------------------- original features
def review_movie(llm, movie_name: str, config: dict | None = None) -> list[str]:
    """Original 50-word bullet review (the 'Quick Critique' task)."""
    prompt = REVIEW_TEMPLATE.invoke({"movie_name": movie_name})
    return to_bullets(to_text(llm.invoke(prompt, config=config).content if config else llm.invoke(prompt).content))


def recommend_movies(llm, user_input: str, n: int, config: dict | None = None) -> list[Movie]:
    chain = RECOMMEND_TEMPLATE | llm.with_structured_output(Recommendations)
    return chain.invoke({"user_input": user_input, "n": n}, config).recommendations


# --------------------------------------------------------------------------- structured critique
def facts_text(meta: MovieMeta | None) -> str:
    """Verified TMDB facts handed to the model so credits are never guessed."""
    if meta is None:
        return ""
    cast = ", ".join(f"{n} as {c}" if c else n for n, c in meta.cast)
    rows = [
        ("Title", meta.title), ("Year", meta.year), ("Runtime", meta.runtime),
        ("Genres", ", ".join(meta.genres)), ("Director", meta.director),
        ("Cinematographer", meta.cinematographer), ("Composer", meta.composer),
        ("Cast", cast), ("Overview", meta.overview),
    ]
    lines = [f"- {k}: {v}" for k, v in rows if v]
    return "\n\nVerified facts (TMDB):\n" + "\n".join(lines) if lines else ""


def critique_movie(llm, movie_name: str, facts: str = "", config: dict | None = None, *, level: str = "none",
                   depth: str = "standard", language: str = "English") -> tuple[Critique, int]:
    """Structured critique. Returns (critique, spoiler_sentences_removed)."""
    chain = CRITIQUE_TEMPLATE | llm.with_structured_output(Critique)
    extra = directives(depth, language) + spoilers.instructions(level)
    result = chain.invoke({"movie_name": movie_name, "facts": facts, "directives": extra}, config)
    if not isinstance(result, Critique):
        raise CritiqueError()
    result.quick_take = to_bullets("\n".join(result.quick_take))
    result.strengths = [s.strip() for s in result.strengths if s.strip()][:3]
    result.flaws = [s.strip() for s in result.flaws if s.strip()][:3]
    result.themes_tags = [t.strip() for t in result.themes_tags if t.strip()][:4]
    removed = spoilers.enforce(result, level)
    return result, removed


@dataclass(frozen=True)
class Reco:
    movie: Movie
    poster_url: str = ""


@dataclass(frozen=True)
class Analysis:
    query: str
    critique: Critique
    meta: MovieMeta | None = None
    recos: tuple[Reco, ...] = ()
    run: PipelineRun | None = None
    alternatives: tuple[Candidate, ...] = ()   # same-title films TMDB also matched
    notices: tuple[str, ...] = ()
    model_used: str = ""                       # "Provider:model" that actually produced the critique
    fallback: str = ""                         # "primary → fallback" when a fallback model was used
    spoiler_level: str = "none"
    spoiler_removed: int = 0                   # sentences removed by the spoiler safety filter
    created_at: float = 0.0
    from_storage: bool = False

    @property
    def cached(self) -> bool:
        return bool(self.run and self.run.stage("analysis").cached)


def exclude_titles(recos: list[Movie], *titles: str) -> list[Movie]:
    banned = {normalize_title(t) for t in titles if t}
    return [m for m in recos if normalize_title(m.title) not in banned]


# --------------------------------------------------------------------------- pipeline stages
def _data_branch(run: PipelineRun, query: str, tmdb_key: str, secrets: list[str]):
    """search -> TMDB details -> processing. Failures degrade to AI-only; never abort."""
    if not tmdb_key:
        run.skip("search", "No TMDB key configured; credits will be AI-supplied")
        run.skip("tmdb", "Skipped: no TMDB key")
        run.skip("process", "Skipped: no TMDB data")
        return None, ()
    title, year = parse_title_year(query)
    selection = None
    try:
        with stage_scope(run, "search"):
            cands = call_with_retries(lambda: search_movies(title, tmdb_key, year),
                                      run=run, stage="search", source="tmdb", secrets=secrets)
            selection = choose_candidate(cands, title, year)
            if selection is None:
                raise AppError(ErrorCategory.TMDB, f"TMDB has no match for “{title}”. Check the spelling or add the year.",
                               stage="search", source="tmdb")
            b = selection.best
            run.complete("search", note=f"{len(cands)} matches; chose {b.title} ({b.year or '?'}), TMDB #{b.id}")
    except AppError:
        run.skip("tmdb", "Skipped: movie search failed")
        run.skip("process", "Skipped: no TMDB data")
        return None, ()
    try:
        with stage_scope(run, "tmdb"):
            meta, hit = call_with_retries(lambda: fetch_details(selection.best.id, tmdb_key),
                                          run=run, stage="tmdb", source="tmdb", secrets=secrets)
            run.complete("tmdb", note=f"Details, credits and images for TMDB #{meta.tmdb_id}", cached=hit)
    except AppError:
        run.skip("process", "Skipped: TMDB details unavailable")
        return None, selection.alternatives
    with stage_scope(run, "process"):
        run.complete("process", note=f"{len(meta.cast)} cast, director {'found' if meta.director else 'n/a'}, "
                                     f"rating {'found' if meta.rating else 'n/a'}")
    return meta, selection.alternatives


def _init_branch(run: PipelineRun, gateway: Gateway, task: str):
    """Validate that a model can be used for `task` (key present, package installed, not known-invalid)."""
    try:
        with stage_scope(run, "init"):
            ref = gateway.prepare(task, run, "init")
            run.complete("init", note=f"{ref} ready")
            return ref, None
    except AppError as err:
        return None, err


def _analysis_stage(run, gateway, query, facts, key, cache, secrets, level, depth, language):
    try:
        with stage_scope(run, "analysis"):
            hit = cache.get(key)
            if hit is not None:
                critique, removed, produced = hit
                run.complete("analysis", note=f"Reused an earlier result ({produced})", cached=True)
                return (critique, removed, produced), None
            critique, removed = gateway.call(
                "analysis", lambda llm, cfg: critique_movie(llm, query, facts, cfg, level=level, depth=depth,
                                                            language=language),
                run=run, stage="analysis", secrets=secrets)
            produced = gateway.model_used("analysis")
            if critique.recognized:
                cache.set(key, (critique, removed, produced))  # only complete, validated results are cached
                run.complete("analysis", note=f"Critique for {critique.title or query} by {produced}")
            else:
                run.complete("analysis", note="Film not recognised by the model; no scores generated")
            return (critique, removed, produced), None
    except AppError as err:
        return None, err


def _poster_for(run, movie: Movie, tmdb_key: str, secrets: list[str], stage: str = "recommend") -> str:
    try:
        year = movie.year if movie.year.isdigit() else ""
        cands = call_with_retries(lambda: search_movies(movie.title, tmdb_key, year), run=run,
                                  stage=stage, source="tmdb", secrets=secrets, max_attempts=2)
    except AppError as err:
        run.event(stage, "warn", f"poster lookup failed for {movie.title} [{err.category.value}]")
        return ""
    sel = choose_candidate(cands, movie.title, year)
    return sel.best.poster_url if sel else ""


def _recommend_stage(run, gateway, query, meta, tmdb_key, n, key, cache, secrets):
    """AI recommendations (primary) with real posters; TMDB recommendations as fallback."""
    notices: list[str] = []
    try:
        with stage_scope(run, "recommend"):
            hit = cache.get(key)
            if hit is not None:
                run.complete("recommend", note="Reused an earlier result", cached=True)
                return list(hit), notices
            llm_err = None
            movies: list[Movie] = []
            try:
                movies = gateway.call("recommend", lambda llm, cfg: recommend_movies(
                    llm, f"Movies similar to {query}", n + 2, cfg), run=run, stage="recommend", secrets=secrets)
            except AppError as err:
                llm_err = err
                run.event("recommend", "warn", f"AI recommendations failed [{err.category.value}]")
            movies = exclude_titles(movies, query, meta.title if meta else "")[:n]
            recos: list[Reco] = []
            if movies:
                if tmdb_key:
                    with ThreadPoolExecutor(max_workers=4) as pool:
                        posters = list(pool.map(lambda m: _poster_for(run, m, tmdb_key, secrets), movies))
                else:
                    posters = [""] * len(movies)
                recos = [Reco(m, p) for m, p in zip(movies, posters)]
            elif meta and tmdb_key:
                try:
                    found = call_with_retries(lambda: fetch_recommendations(meta.tmdb_id, tmdb_key, n),
                                              run=run, stage="recommend", source="tmdb", secrets=secrets)
                    recos = [Reco(Movie(title=c.title, year=c.year, genre="", why="Suggested by TMDB for fans of this film."),
                                  c.poster_url) for c in found]
                    if recos:
                        notices.append("Recommendations come from TMDB because the AI recommendation step failed.")
                except AppError:
                    pass
            if not recos:
                raise llm_err or AppError(ErrorCategory.PROVIDER, "No similar films were found.", stage="recommend")
            if llm_err is None:
                cache.set(key, tuple(recos))
            run.complete("recommend", note=f"{len(recos)} films" + (" (TMDB fallback)" if llm_err else ""))
            return recos, notices
    except AppError as err:
        return [], [f"Similar-film recommendations are unavailable: {err.message}"]


def analyze_movie(
    gateway: Gateway,
    query: str,
    *,
    run: PipelineRun | None = None,
    tmdb_key: str = "",
    n_recs: int = NUM_SIMILAR,
    secrets: tuple[str, ...] | list[str] = (),
    spoiler_level: str = "none",
    depth: str = "standard",
    language: str = "English",
    critique_cache: TTLCache = CRITIQUE_CACHE,
    recos_cache: TTLCache = RECOS_CACHE,
) -> Analysis:
    """Run the observable pipeline. Raises a classified AppError only if the AI analysis fails.

    TMDB or recommendation failures degrade gracefully (recorded on `run`, shown as notices).
    """
    level = spoilers.effective_level(spoiler_level)
    model_id = gateway.label("analysis")
    run = run or PipelineRun(query, model_id)
    secrets = [s for s in (*secrets, tmdb_key) if s]
    try:
        query = sanitize_query(query)
    except AppError as err:
        run.fail("search", err)
        for sid in ("tmdb", "process", "init", "analysis", "recommend"):
            run.skip(sid, "Skipped: invalid input")
        run.finish()
        raise

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_data = pool.submit(_data_branch, run, query, tmdb_key, secrets)
        f_init = pool.submit(_init_branch, run, gateway, "analysis")
        (meta, alternatives), (ref, init_err) = f_data.result(), f_init.result()

    if ref is None:
        for sid in ("analysis", "recommend"):
            run.skip(sid, "Skipped: AI model unavailable")
        run.finish()
        raise init_err

    facts = facts_text(meta)
    ident = str(meta.tmdb_id) if meta else normalize_title(query)
    ckey = ("critique", ident, model_id, PROMPT_VERSION, bool(facts), level, depth, language)
    rkey = ("recos", ident, gateway.label("recommend"), PROMPT_VERSION, n_recs, bool(tmdb_key))
    if n_recs <= 0:
        with ThreadPoolExecutor(max_workers=1) as pool:
            f_c = pool.submit(_analysis_stage, run, gateway, query, facts, ckey, critique_cache, secrets,
                              level, depth, language)
            result, c_err = f_c.result()
        run.skip("recommend", "Skipped: not requested")
        recos, notices = [], []
    else:
        with ThreadPoolExecutor(max_workers=2) as pool:
            f_c = pool.submit(_analysis_stage, run, gateway, query, facts, ckey, critique_cache, secrets,
                              level, depth, language)
            f_r = pool.submit(_recommend_stage, run, gateway, query, meta, tmdb_key, n_recs, rkey, recos_cache,
                              secrets)
            (result, c_err), (recos, notices) = f_c.result(), f_r.result()

    run.finish()
    if result is None:
        raise c_err
    critique, removed, produced = result
    banned = {normalize_title(critique.title)} if critique.title else set()
    recos = [r for r in recos if normalize_title(r.movie.title) not in banned]
    notes = list(notices)
    if removed:
        notes.append(f"{removed} sentence(s) were removed by the spoiler filter to keep this analysis spoiler-free.")
    fallback = gateway.fallback_used.get("analysis", "")
    if fallback and not (run.stage("analysis").cached):
        notes.append(f"The configured fallback model produced this analysis ({fallback}).")
    return Analysis(query=query, critique=critique, meta=meta, recos=tuple(recos), run=run,
                    alternatives=alternatives, notices=tuple(notes), model_used=produced, fallback=fallback,
                    spoiler_level=level, spoiler_removed=removed, created_at=time.time())


def sanitize_taste(text: str, max_chars: int = 300) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()[:max_chars]
    if not cleaned:
        raise InvalidInputError("Describe a movie, mood, or genre first.", stage="input")
    return cleaned


def discover_movies(
    gateway: Gateway,
    text: str,
    *,
    run: PipelineRun,
    tmdb_key: str = "",
    n: int = 6,
    secrets: tuple[str, ...] | list[str] = (),
) -> list[Reco]:
    """Observable taste-based pipeline: input -> AI setup -> AI picks -> TMDB posters.

    Raises a classified AppError if the picks cannot be produced; poster problems only degrade.
    """
    secrets = [s for s in (*secrets, tmdb_key) if s]
    try:
        with stage_scope(run, "input"):
            text = sanitize_taste(text)
            run.complete("input", note=f"{len(text)} characters")
    except AppError:
        for sid in ("init", "recommend", "posters"):
            run.skip(sid, "Skipped: invalid input")
        run.finish()
        raise
    ref, init_err = _init_branch(run, gateway, "recommend")
    if ref is None:
        for sid in ("recommend", "posters"):
            run.skip(sid, "Skipped: AI model unavailable")
        run.finish()
        raise init_err
    try:
        with stage_scope(run, "recommend"):
            movies = gateway.call("recommend", lambda llm, cfg: recommend_movies(llm, text, n, cfg), run=run,
                                  stage="recommend", secrets=secrets)
            if not movies:
                raise AppError(ErrorCategory.MALFORMED, "The model returned no picks. Please try again.",
                               retryable=True, stage="recommend", source="ai")
            run.complete("recommend", note=f"{len(movies)} films suggested by {gateway.model_used('recommend')}")
    except AppError:
        run.skip("posters", "Skipped: no picks to look up")
        run.finish()
        raise
    if not tmdb_key:
        run.skip("posters", "No TMDB key configured; using designed placeholders")
        posters = [""] * len(movies)
    else:
        try:
            with stage_scope(run, "posters"):
                with ThreadPoolExecutor(max_workers=4) as pool:
                    posters = list(pool.map(lambda m: _poster_for(run, m, tmdb_key, secrets, "posters"), movies))
                found = sum(bool(p) for p in posters)
                if found == 0:
                    raise AppError(ErrorCategory.TMDB, "No posters could be fetched from TMDB.",
                                   stage="posters", source="tmdb")
                run.complete("posters", note=f"{found} of {len(movies)} posters found")
        except AppError:
            posters = [""] * len(movies)   # picks still display with placeholders
    run.finish()
    return [Reco(m, p) for m, p in zip(movies, posters)]


# --------------------------------------------------------------------------- search assistance (AI, on demand only)
def suggest_titles(gateway: Gateway, description: str, tmdb_key: str, *, secrets=(), n: int = 5) -> list[Candidate]:
    """Recall a film from a vague description. The AI only proposes titles; each is verified on TMDB."""
    text = sanitize_taste(description)
    movies = gateway.call("search_assist", lambda llm, cfg: (SEARCH_ASSIST_TEMPLATE | llm.with_structured_output(
        Recommendations)).invoke({"description": text, "n": n}, cfg).recommendations, stage="search_assist",
        secrets=secrets)
    found: list[Candidate] = []
    for m in movies[:n]:
        year = m.year if m.year.isdigit() else ""
        cands = call_with_retries(lambda: search_movies(m.title, tmdb_key, year), stage="search_assist", source="tmdb",
                                  secrets=[tmdb_key], max_attempts=2)
        sel = choose_candidate(cands, m.title, year)
        if sel and sel.best.id not in {c.id for c in found}:
            found.append(sel.best)      # only titles TMDB actually has are shown
    return found


def extract_filters(gateway: Gateway, request: str, genre_names: list[str], *, secrets=()) -> SearchFilters:
    """Natural-language request -> structured filters (the 'Structured Metadata Extraction' task)."""
    text = sanitize_taste(request)
    result = gateway.call("extract", lambda llm, cfg: (EXTRACT_TEMPLATE | llm.with_structured_output(
        SearchFilters)).invoke({"request": text, "genres": ", ".join(genre_names)}, cfg), stage="extract",
        secrets=secrets)
    if not isinstance(result, SearchFilters):
        raise CritiqueError("The model returned unusable filters.")
    allowed = {g.lower(): g for g in genre_names}
    result.genres = [allowed[g.lower()] for g in result.genres if g.lower() in allowed][:3]
    this_year = time.gmtime().tm_year + 1
    result.year_from = result.year_from if 1888 <= result.year_from <= this_year else 0
    result.year_to = result.year_to if 1888 <= result.year_to <= this_year else 0
    if not (len(result.language) == 2 and result.language.isalpha()):
        result.language = ""
    result.language = result.language.lower()
    return result
