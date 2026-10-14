"""Shared Streamlit widgets used by several pages."""
from __future__ import annotations

import streamlit as st

from .. import scoring, spoilers
from ..config import DIMENSIONS, SCORE_SCALES
from ..errors import CATEGORY_LABELS, AppError, ErrorCategory
from ..features.serialize import analysis_key, analysis_to_dict, meta_snapshot
from ..pipeline import diagnostics_text
from ..services import Analysis
from .components import compact, critique_grid_html, esc, featured_html, verdict_html
from .runtime import Ctx
from .state import goto, workspace


def header(title: str, subtitle: str = "") -> None:
    sub = f"<p>{esc(subtitle)}</p>" if subtitle else ""
    st.markdown(compact(f'<div class="page-head"><h1>{esc(title)}</h1>{sub}</div>'), unsafe_allow_html=True)


def eyebrow(text: str) -> None:
    st.markdown(f'<div class="eyebrow">{esc(text)}</div>', unsafe_allow_html=True)


def show_error(err: AppError, *, run=None, key: str = "err") -> None:
    """Friendly message + a copyable, redacted diagnostics block. Never shows keys."""
    st.error(f"**{CATEGORY_LABELS.get(err.category, 'Error')}.** {err.message}", icon=":material/error:")
    if err.category in (ErrorCategory.AUTH, ErrorCategory.MODEL, ErrorCategory.BUDGET):
        st.button("Open AI Control Center", key=f"{key}_cc", on_click=goto, args=("control",),
                  icon=":material/tune:")
    if run is not None:
        with st.expander("Diagnostics (safe to share)"):
            st.code(diagnostics_text(run), language="text")


def need_tmdb(ctx: Ctx, what: str) -> bool:
    """Show a setup hint and return False when TMDB is not configured."""
    if ctx.tmdb_key:
        return True
    st.info(f"{what} needs a TMDB key (free). Add it in AI Control Center → API Keys. "
            "AI critiques work without it, but credits and posters will be AI-supplied or missing.",
            icon=":material/key:")
    st.button("Add TMDB key", key=f"need_tmdb_{abs(hash(what))}", on_click=goto, args=("control",))
    return False


def need_ai(ctx: Ctx, task: str) -> bool:
    """Check the task's primary/fallback model can be used; show setup guidance if not."""
    try:
        ctx.gateway.prepare(task)
        return True
    except AppError as err:
        show_error(err, key=f"need_ai_{task}")
        return False


def score_controls(ctx: Ctx, key: str) -> tuple[int, dict[str, float]]:
    """Scale selector and transparent weight sliders (session-local until saved)."""
    p = ctx.prefs
    scale = st.session_state.get(f"{key}_scale", p["score_scale"])
    weights = dict(st.session_state.get(f"{key}_weights", p["weights"]))
    with st.expander("Scorecard settings — scale and category weights"):
        scale = st.radio("Display scale", SCORE_SCALES, index=SCORE_SCALES.index(scale), horizontal=True,
                         key=f"{key}_scale_w", format_func=lambda s: f"0–{s}")
        st.caption("Scores are stored on a 0–10 scale and only converted for display.")
        cols = st.columns(4)
        for i, (k, title) in enumerate(DIMENSIONS):
            weights[k] = cols[i % 4].slider(scoring.label(k), 0.0, 5.0, float(weights.get(k, 1.0)), 0.25,
                                            key=f"{key}_w_{k}")
        if sum(weights.values()) <= 0:
            st.warning("All weights are zero; defaults are used.")
            weights = {k: 1.0 for k, _ in DIMENSIONS}
        c1, c2 = st.columns(2)
        if c1.button("Save as my defaults", key=f"{key}_save_w"):
            from .runtime import save_prefs
            save_prefs(score_scale=scale, weights=weights)
            st.toast("Saved to this session's preferences.")
        if c2.button("Reset", key=f"{key}_reset_w"):
            for k, _ in DIMENSIONS:
                st.session_state.pop(f"{key}_w_{k}", None)
            st.rerun()
    st.session_state[f"{key}_scale"], st.session_state[f"{key}_weights"] = scale, weights
    return scale, weights


def ratings_panel(a: Analysis, scale: int, weights: dict, user_rating: float | None) -> None:
    """Keeps AI scores, external ratings and the user's own rating visibly separate."""
    c, m = a.critique, a.meta
    dims = scoring.dimension_scores(c)
    weighted, used, missing = scoring.weighted_overall(dims, weights)
    ai_overall = scoring.valid_score(c.overall_score)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("AI verdict score", f"{scoring.fmt(ai_overall, scale)}/{scale}",
              help="The model's own holistic judgement (AI-generated, subjective).")
    c2.metric("AI weighted score", f"{scoring.fmt(weighted, scale)}/{scale}",
              help=f"Computed from the category scores with your weights ({len(used)} of {len(DIMENSIONS)} scored).")
    c3.metric("TMDB audience (external)", f"{m.rating:.1f}/10" if m and m.rating else "—",
              help="Average of TMDB users. Not a CineCritic score." + (f" {m.votes:,} votes." if m else ""))
    c4.metric("Your rating", f"{scoring.fmt(user_rating, scale)}/{scale}" if user_rating is not None else "—",
              help="Your personal rating from your archive.")
    note = f"Weighted score renormalises over scored categories; band: {scoring.band(weighted)}."
    if missing:
        note += " Not assessed: " + ", ".join(scoring.label(k) for k in missing) + "."
    st.caption(note)


def spoiler_gate(a: Analysis, film_key: str) -> None:
    """Spoiler notes stay hidden until the user explicitly asks for them."""
    notes = (a.critique.spoiler_notes or "").strip()
    if a.spoiler_level == "none" or not notes:
        st.caption(":material/shield: This analysis is spoiler-free. Change spoiler protection in "
                   "AI Control Center → Analysis Preferences, or per film on the Film Critique page.")
        return
    if film_key in st.session_state.revealed:
        st.warning(f"Spoilers ({spoilers.LABELS[a.spoiler_level]})", icon=":material/visibility:")
        st.write(notes)
        if st.button("Hide spoilers", key=f"hide_{film_key}"):
            st.session_state.revealed.discard(film_key)
            st.rerun()
    else:
        st.markdown('<div class="spoiler-veil">Spoiler notes are hidden.</div>', unsafe_allow_html=True)
        if st.button("Reveal spoiler notes", key=f"reveal_{film_key}", icon=":material/visibility:"):
            st.session_state.revealed.add(film_key)
            st.rerun()


def show_analysis(a: Analysis, ctx: Ctx, *, key: str = "cur", reveal_motion: bool = True) -> None:
    """Featured card, scorecards, verdict, rating separation, spoiler gate."""
    fkey = analysis_key(a)
    ws = workspace()
    entry = ws.get_archive_entry(fkey)
    scale, weights = score_controls(ctx, "sc")
    for n in a.notices:
        st.info(n, icon=":material/info:")
    st.markdown(compact(featured_html(a, scale)), unsafe_allow_html=True)
    ratings_panel(a, scale, weights, entry["rating"] if entry else None)
    st.markdown(f'<div class="{"reveal" if reveal_motion else ""}">{compact(critique_grid_html(a, scale, weights))}</div>',
                unsafe_allow_html=True)
    st.markdown(compact(verdict_html(a, scale)), unsafe_allow_html=True)
    if a.critique.themes_tags:
        st.caption("Themes (AI interpretation): " + " · ".join(a.critique.themes_tags))
    spoiler_gate(a, fkey)
    if a.model_used:
        st.caption(f"Generated by {a.model_used}" + (f" (fallback used: {a.fallback})" if a.fallback else "")
                   + ("" if not a.from_storage else " · restored from this session"))


def save_to_archive(a: Analysis, ctx: Ctx, status: str = "planned") -> str:
    """Store the analysis (versioned) and make sure the film is in the archive."""
    ws = workspace()
    fkey = analysis_key(a)
    snap = meta_snapshot(a)
    ws.upsert_archive(fkey, snap["title"], year=snap["year"], status=None if ws.get_archive_entry(fkey) else status,
                      meta=snap)
    return fkey


def store_analysis(a: Analysis, ws=None) -> str:
    """Save a versioned analysis. Pass `ws` when calling from a worker thread."""
    from ..config import PROMPT_VERSION
    ws = ws or workspace()
    fkey = analysis_key(a)
    ws.save_analysis(fkey, analysis_to_dict(a), model_id=a.model_used, spoiler_level=a.spoiler_level,
                     prompt_version=PROMPT_VERSION)
    return fkey


# --------------------------------------------------------------------------- film cards
def candidate_card(c, key: str, genres: dict | None = None, *, saved: bool = False) -> None:
    """One TMDB result with Analyze / Save actions. TMDB rating is labelled as external."""
    from ..features.quests import meta_from_candidate
    from .components import POSTER_GRADIENTS, safe_image_url
    poster = safe_image_url(c.poster_url)
    inner = (f'<img src="{poster}" alt="Poster for {esc(c.title)}" loading="lazy">' if poster else
             f'<div class="ph" style="background:{POSTER_GRADIENTS[c.id % len(POSTER_GRADIENTS)]}">'
             f'<span>{esc(c.title[:1].upper())}</span></div>')
    rating = f"TMDB {c.rating:.1f}" if c.rating else ""
    meta = " · ".join(x for x in (esc(c.year), rating) if x)
    names = [genres[g] for g in c.genre_ids if genres and g in genres][:2]
    blurb = esc(c.overview[:140] + ("…" if len(c.overview) > 140 else ""))
    st.markdown(compact(f'<article class="reco"><div class="poster">{inner}</div><div class="reco-body">'
                        f'<div class="reco-meta">{meta}</div><h3>{esc(c.title)}</h3>'
                        f'<div class="reco-meta">{esc(", ".join(names))}</div><p>{blurb}</p></div></article>'),
                unsafe_allow_html=True)
    q = f"{c.title} ({c.year})" if c.year else c.title
    b1, b2 = st.columns(2)
    b1.button("Analyze", key=f"{key}_an", on_click=goto, args=("critique",), kwargs={"critique_query": q},
              use_container_width=True)
    fkey = f"tmdb:{c.id}"
    have = workspace().get_archive_entry(fkey) is not None
    if b2.button("Saved ✓" if have else "Save", key=f"{key}_sv", disabled=have, use_container_width=True,
                 help="Add to your archive as 'planned'"):
        try:
            workspace().upsert_archive(fkey, c.title, year=c.year, status="planned", meta=meta_from_candidate(c, genres))
            st.toast(f"{c.title} saved to your archive.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
