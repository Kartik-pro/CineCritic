"""Intelligence › Head-to-Head Movie Battles."""
from __future__ import annotations

import streamlit as st

from .. import scoring
from ..config import DIMENSIONS, PROMPT_VERSION
from ..features import exports
from ..features.battles import run_battle
from ..features.serialize import analysis_from_dict, analysis_to_dict, analysis_key
from ..pipeline import PipelineRun
from ..ui.common import header, score_controls, show_error, store_analysis
from ..ui.components import compact, esc
from ..ui.live import run_live, show_events
from ..ui.runtime import get_ctx
from ..ui.state import workspace

WORDING = {"a": "{a} leads on CineCritic's scores", "b": "{b} leads on CineCritic's scores",
           "too_close": "Too close to call on CineCritic's scores",
           "inconclusive": "Inconclusive: not enough comparable categories"}


def _load(ws, key: str, level: str):
    item = ws.latest_analysis(key, spoiler_level=level, prompt_version=PROMPT_VERSION)
    if not item:
        return None
    try:
        return analysis_from_dict(item["payload"])
    except ValueError:
        return None


def _show(b, scale: int, weights: dict) -> None:
    a, c, comp = b.a, b.b, b.comparison
    ta, tb = a.critique.title or a.query, c.critique.title or c.query
    st.markdown(f"### {esc(ta)} vs {esc(tb)}")
    st.success(WORDING[comp.leader].format(a=ta, b=tb) +
               f" · weighted {scoring.fmt(comp.overall_a, scale)} vs {scoring.fmt(comp.overall_b, scale)} (/{scale})")
    st.caption(comp.rule + " This is a score-based reading of AI assessments, not a verdict on artistic merit.")
    rows = []
    mark = {"a": f"◀ {ta}", "b": f"{tb} ▶", "tie": "Tie", "insufficient": "Not comparable"}
    for r in comp.dims:
        rows.append({"Category": scoring.label(r.key), ta: scoring.fmt(r.a, scale), tb: scoring.fmt(r.b, scale),
                     "Result": mark[r.outcome], "Gap": f"{r.gap * scale / 10:.1f}" if r.gap is not None else "—"})
    st.dataframe(rows, hide_index=True, use_container_width=True)
    if b.narrative:
        st.markdown("#### Written comparison (AI)")
        st.write(b.narrative)
    for n in b.notices:
        st.info(n)
    try:
        st.download_button("Download comparison PDF", exports.comparison_pdf(b, scale=scale, weights=weights),
                           file_name="cinecritic-battle.pdf", mime="application/pdf", icon=":material/picture_as_pdf:")
    except Exception as exc:
        st.caption(f"PDF unavailable: {getattr(exc, 'message', type(exc).__name__)}")


def render() -> None:
    ctx = get_ctx()
    header("Head-to-Head Movie Battles",
           "Two films, eight craft categories, a transparent tally. Stored analyses are reused, so repeat battles are cheap.")
    scale, weights = score_controls(ctx, "bt")
    with st.form("battle_form", border=False):
        c1, c2, c3 = st.columns([3, 3, 1], vertical_alignment="bottom")
        qa = c1.text_input("Film A", key="bt_a", max_chars=120, placeholder="Heat (1995)")
        qb = c2.text_input("Film B", key="bt_b", max_chars=120, placeholder="Collateral (2004)")
        go = c3.form_submit_button("Battle", type="primary", use_container_width=True)
    if go:
        if not qa.strip() or not qb.strip():
            st.warning("Enter two films.")
        else:
            run = PipelineRun(f"{qa.strip()} vs {qb.strip()}"[:60], ctx.gateway.label("analysis"), kind="battle")
            slot, level, ws = st.empty(), ctx.level, ctx.ws
            result, err = run_live(run, lambda: run_battle(
                ctx.gateway, qa.strip(), qb.strip(), run=run, tmdb_key=ctx.tmdb_key, secrets=ctx.secrets,
                weights=weights, level=level, depth=ctx.prefs["analysis_depth"], language=ctx.prefs["language"],
                load=lambda k, lv: _load(ws, k, lv), save=lambda an: store_analysis(an, ws)), secrets=ctx.secrets, slot=slot)
            if err:
                st.session_state.battle = None
                show_error(err, run=run, key="bt_err")
            else:
                st.session_state.battle = result
                show_events(run)
    battle = st.session_state.battle
    if battle is not None:
        _show(battle, scale, weights)
