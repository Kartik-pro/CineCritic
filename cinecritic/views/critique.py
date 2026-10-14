"""Cinema › Film Critique."""
from __future__ import annotations

import streamlit as st

from .. import spoilers
from ..config import EXAMPLE_FILMS, MAX_QUERY_CHARS, PROMPT_VERSION, TASKS
from ..features import exports
from ..features.serialize import analysis_from_dict, analysis_key, film_key
from ..pipeline import PipelineRun
from ..services import analyze_movie
from ..ui.common import (header, need_tmdb, save_to_archive, show_analysis, show_error, store_analysis)
from ..ui.components import compact, empty_state_html, esc, hero_html, reco_card_html, recos_header_html, timing_html
from ..ui.live import run_live, show_events
from ..ui.runtime import get_ctx
from ..ui.state import goto, take_handoff, workspace


def _queue(title: str) -> None:
    st.session_state.critique_q = title
    st.session_state.critique_go = True


def _run(query: str, level: str, ctx) -> None:
    ws = workspace()
    try:
        model_id = ctx.gateway.label("analysis")
    except Exception:
        model_id = ""
    run = PipelineRun(query, model_id)
    slot = st.empty()
    depth, language = ctx.prefs["analysis_depth"], ctx.prefs["language"]
    result, err = run_live(
        run, lambda: analyze_movie(ctx.gateway, query, run=run, tmdb_key=ctx.tmdb_key, secrets=ctx.secrets,
                                   spoiler_level=level, depth=depth, language=language),
        secrets=ctx.secrets, slot=slot)
    if err is not None:
        st.session_state.current = None
        show_error(err, run=run, key="crit")
        return
    if not result.critique.recognized:
        st.session_state.current = None
        st.warning(f"“{query}” was not recognised as a released film. Check the spelling or add the year, "
                   "for example “Heat (1995)”.")
        return
    store_analysis(result)
    st.session_state.current = result
    st.session_state.crit_run = run


def _actions(a, ctx) -> None:
    ws = workspace()
    fkey = analysis_key(a)
    entry = ws.get_archive_entry(fkey)
    scale = st.session_state.get("sc_scale", ctx.prefs["score_scale"])
    weights = st.session_state.get("sc_weights", ctx.prefs["weights"])
    st.markdown("### Your archive")
    c1, c2, c3 = st.columns([1, 1, 2])
    status = c1.selectbox("Status", ("planned", "watching", "watched"),
                          index=("planned", "watching", "watched").index(entry["status"]) if entry else 0,
                          key=f"crit_status_{fkey}")
    current = entry["rating"] if entry and entry["rating"] is not None else 7.0
    rate = c2.checkbox("I have a rating", value=bool(entry and entry["rating"] is not None), key=f"crit_hasr_{fkey}")
    rating = c3.slider("Your rating (0–10)", 0.0, 10.0, float(current), 0.5, key=f"crit_r_{fkey}",
                       disabled=not rate)
    b1, b2 = st.columns(2)
    if b1.button("Save to my archive", key=f"crit_save_{fkey}", type="primary", icon=":material/bookmark_add:"):
        try:
            save_to_archive(a, ctx, status)
            ws.upsert_archive(fkey, a.critique.title or a.query, status=status, rating=rating if rate else None)
            st.toast("Saved to your archive (this session).")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    if b2.button("Ask the Critic about this film", key=f"crit_ask_{fkey}", icon=":material/forum:"):
        st.session_state.ask_film = fkey
        goto("ask")
        st.rerun()
    st.markdown("### Export")
    include = st.checkbox("Include spoiler notes in exports", value=False, key="crit_exp_spoil",
                          disabled=a.spoiler_level == "none" or not a.critique.spoiler_notes)
    d1, d2 = st.columns(2)
    try:
        pdf = exports.critique_pdf(a, scale=scale, weights=weights, include_spoilers=include,
                                   user_rating=rating if rate else (entry or {}).get("rating"))
        d1.download_button("Download PDF report", pdf, file_name=f"cinecritic-{fkey.replace(':', '-')}.pdf",
                           mime="application/pdf", icon=":material/picture_as_pdf:", key="crit_pdf")
    except Exception as exc:  # report generation must never break the page
        d1.caption(f"PDF unavailable: {getattr(exc, 'message', type(exc).__name__)}")
    d2.download_button("Download JSON", exports.analysis_json(a, include_spoilers=include),
                       file_name=f"cinecritic-{fkey.replace(':', '-')}.json", mime="application/json",
                       icon=":material/data_object:", key="crit_json")


def _versions(a) -> None:
    ws = workspace()
    fkey = analysis_key(a)
    versions = ws.analysis_versions(fkey)
    if len(versions) < 2:
        return
    with st.expander(f"Saved versions of this analysis ({len(versions)})"):
        for v in versions:
            when = __import__("datetime").datetime.fromtimestamp(v["created_at"]).strftime("%Y-%m-%d %H:%M")
            c1, c2 = st.columns([4, 1])
            c1.write(f"v{v['version']} · {v['model_id'] or 'unknown model'} · {spoilers.LABELS.get(v['spoiler_level'], '')} · {when}")
            if c2.button("Open", key=f"ver_{fkey}_{v['version']}"):
                item = ws.get_analysis(fkey, v["version"])
                try:
                    st.session_state.current = analysis_from_dict(item["payload"])
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))


def render() -> None:
    ctx = get_ctx()
    ss = st.session_state
    handoff = take_handoff("critique_query")
    if handoff:
        _queue(handoff)
    st.markdown(compact(hero_html()), unsafe_allow_html=True)

    levels = spoilers.LEVELS
    with st.container(key="hero_search"):
        with st.form("critique_form", border=False):
            c1, c2 = st.columns([5, 1], vertical_alignment="center")
            c1.text_input("Film", key="critique_q", max_chars=MAX_QUERY_CHARS, label_visibility="collapsed",
                          placeholder="Search a film — e.g. Oppenheimer (2023)")
            go = c2.form_submit_button("Analyze", type="primary", use_container_width=True)
    level = st.selectbox("Spoiler protection for this analysis", levels,
                         index=levels.index(ctx.level), format_func=lambda x: spoilers.LABELS[x],
                         key="crit_level", help="Default is spoiler-free. Spoiler notes, when enabled, stay "
                                                "hidden until you reveal them.")
    if level != "none":
        st.caption(":material/warning: Spoiler notes will be generated but kept hidden until you click Reveal.")

    with st.container(key="chips"):
        cols = st.columns(len(EXAMPLE_FILMS))
        for col, film in zip(cols, EXAMPLE_FILMS):
            col.button(film, key=f"chip_{film}", on_click=_queue, args=(film,))
    if not ctx.tmdb_key:
        need_tmdb(ctx, "Verified credits and posters")

    run_now = go or ss.pop("critique_go", False)
    if run_now and ss.get("critique_q", "").strip():
        _run(ss.critique_q.strip(), level, ctx)
    elif ss.get("last_run") is not None and ss.current is None and not run_now:
        pass

    a = ss.current
    if a is None:
        st.markdown(compact(empty_state_html()), unsafe_allow_html=True)
        return
    for alt in a.alternatives[:3]:
        st.button(f"Not this one? Analyze {alt.title} ({alt.year})", key=f"alt_{alt.id}", on_click=_queue,
                  args=(f"{alt.title} ({alt.year})" if alt.year else alt.title,))
    show_analysis(a, ctx)
    st.markdown(compact(timing_html(a)), unsafe_allow_html=True)
    if ss.get("crit_run") is not None and ss.crit_run is a.run:
        show_events(a.run)
    if a.recos:
        st.markdown(compact(recos_header_html("Similar films")), unsafe_allow_html=True)
        cols = st.columns(min(4, len(a.recos)))
        for i, (col, r) in enumerate(zip(cols, a.recos)):
            col.markdown(compact(reco_card_html(r, i)), unsafe_allow_html=True)
            col.button("Analyze", key=f"reco_{i}_{r.movie.title}", on_click=_queue,
                       args=(f"{r.movie.title} ({r.movie.year})" if r.movie.year else r.movie.title,))
    _actions(a, ctx)
    _versions(a)
