"""Cinema › Film Discovery: TMDB browsing, AI taste picks and plain-English filters."""
from __future__ import annotations

import streamlit as st

from .. import metadata
from ..config import LANGUAGES
from ..errors import AppError, classify
from ..features.quests import LANGUAGE_NAMES
from ..pipeline import PipelineRun
from ..services import discover_movies, extract_filters
from ..ui.common import candidate_card, header, need_tmdb, show_error
from ..ui.components import compact, reco_card_html
from ..ui.live import run_live, show_events
from ..ui.runtime import get_ctx
from ..ui.state import goto, workspace

KINDS = {"popular": "Popular now", "trending": "Trending this week", "top_rated": "Top rated",
         "now_playing": "In cinemas", "filtered": "Custom filters"}


def _grid(items, key: str, genres: dict) -> None:
    if not items:
        st.info("No films matched. Try loosening a filter.")
        return
    for start in range(0, len(items), 4):
        cols = st.columns(4)
        for col, c in zip(cols, items[start:start + 4]):
            with col:
                candidate_card(c, f"{key}_{c.id}", genres)


def _genres(ctx) -> dict:
    try:
        return metadata.genre_map(ctx.tmdb_key)
    except AppError:
        return {}


def _browse(ctx) -> None:
    if not need_tmdb(ctx, "Browsing real TMDB listings"):
        return
    genres = _genres(ctx)
    kind = st.radio("Listing", list(KINDS), format_func=KINDS.get, horizontal=True, key="disc_kind")
    kwargs: dict = {}
    if kind == "filtered":
        c1, c2, c3, c4 = st.columns(4)
        picked = c1.multiselect("Genres (all must match)", sorted(genres.values()), key="disc_genres")
        by_name = {v: k for k, v in genres.items()}
        y0, y1 = c2.slider("Release years", 1920, 2026, (1990, 2026), key="disc_years")
        lang = c3.selectbox("Original language", [""] + list(LANGUAGE_NAMES), key="disc_lang",
                            format_func=lambda x: LANGUAGE_NAMES.get(x, "Any"))
        sort = c4.selectbox("Sort by", list(metadata.SORTS), key="disc_sort")
        kwargs = {"genre_ids": tuple(by_name[g] for g in picked), "year_from": y0, "year_to": y1,
                  "language": lang, "sort": metadata.SORTS[sort]}
    page = st.number_input("Page", 1, 20, 1, key="disc_page")
    try:
        with st.spinner("Loading from TMDB…"):
            result = metadata.discover_page(ctx.tmdb_key, kind, int(page), **kwargs)
    except AppError as err:
        show_error(err, key="disc_browse")
        return
    st.caption(f"{result.total_results:,} films · page {result.page} of {min(result.total_pages, 500)} · data: TMDB")
    _grid(result.items, "br", genres)


def _taste(ctx) -> None:
    st.write("Describe what you like. The AI proposes titles; posters and years are verified on TMDB when a key is set.")
    text = st.text_area("Your taste", key="disc_taste", max_chars=300, height=90,
                        placeholder="Slow-burn sci-fi with big ideas, like Arrival and Ex Machina")
    if st.button("Find films", type="primary", key="disc_taste_go", icon=":material/auto_awesome:"):
        if not text.strip():
            st.warning("Describe your taste first.")
        else:
            run = PipelineRun(text.strip(), ctx.gateway.label("recommend"), kind="discover")
            slot = st.empty()
            result, err = run_live(run, lambda: discover_movies(ctx.gateway, text, run=run, tmdb_key=ctx.tmdb_key,
                                                                secrets=ctx.secrets, n=6),
                                   secrets=ctx.secrets, slot=slot)
            if err:
                st.session_state.disc = {}
                show_error(err, run=run, key="disc_taste_err")
            else:
                st.session_state.disc = {"recos": result}
    recos = st.session_state.disc.get("recos") or []
    for start in range(0, len(recos), 3):
        cols = st.columns(3)
        for i, (col, r) in enumerate(zip(cols, recos[start:start + 3])):
            with col:
                col.markdown(compact(reco_card_html(r, start + i)), unsafe_allow_html=True)
                q = f"{r.movie.title} ({r.movie.year})" if r.movie.year else r.movie.title
                col.button("Analyze", key=f"taste_{start + i}", on_click=goto, args=("critique",),
                           kwargs={"critique_query": q})


def _plain(ctx) -> None:
    if not need_tmdb(ctx, "Plain-English discovery"):
        return
    genres = _genres(ctx)
    text = st.text_input("What are you in the mood for?", key="disc_plain", max_chars=200,
                         placeholder="Korean thrillers from the 2010s")
    if st.button("Search", key="disc_plain_go", type="primary", icon=":material/search:") and text.strip():
        try:
            with st.spinner("Turning your request into filters…"):
                f = extract_filters(ctx.gateway, text, sorted(genres.values()), secrets=ctx.secrets)
        except Exception as exc:
            show_error(exc if isinstance(exc, AppError) else classify(exc, source="ai", secrets=ctx.secrets),
                       key="disc_plain_err")
            return
        by_name = {v.lower(): k for k, v in genres.items()}
        st.session_state.disc = {"filters": f, "ids": tuple(by_name[g.lower()] for g in f.genres if g.lower() in by_name)}
    d = st.session_state.disc
    if d.get("filters") is not None:
        f = d["filters"]
        st.caption("Interpreted as — genres: " + (", ".join(f.genres) or "any") +
                   f" · years: {f.year_from or 'any'}–{f.year_to or 'any'} · language: "
                   f"{LANGUAGE_NAMES.get(f.language, f.language) or 'any'}. These filters were produced by AI; "
                   "the films come from TMDB.")
        try:
            page = metadata.discover_page(ctx.tmdb_key, "filtered", 1, genre_ids=d["ids"], year_from=f.year_from or None,
                                          year_to=f.year_to or None, language=f.language,
                                          sort="vote_average.desc")
        except AppError as err:
            show_error(err, key="disc_plain_page")
            return
        _grid(page.items, "pl", genres)


def render() -> None:
    ctx = get_ctx()
    header("Film Discovery", "Browse real TMDB listings, get AI taste picks, or just describe a mood.")
    t1, t2, t3 = st.tabs(["Browse TMDB", "AI taste picks", "Plain-English search"])
    with t1:
        _browse(ctx)
    with t2:
        _taste(ctx)
    with t3:
        _plain(ctx)
