"""Cinema › Home: a command center built only from this session's real data."""
from __future__ import annotations

import streamlit as st

from .. import metadata, scoring
from ..config import DIMENSIONS, EXAMPLE_FILMS, MAX_QUERY_CHARS
from ..features import graph as g
from ..features.serialize import analysis_from_dict
from ..spoilers import LABELS as SPOILER_LABELS
from ..ui.components import compact, esc, fmt_dur, fmt_score
from ..ui.runtime import get_ctx
from ..ui.state import goto


def _hero() -> None:
    st.markdown(compact("""
    <section class="nhero">
      <div class="kick"><span class="pill gold">AI film intelligence</span><small>Critique · Discovery · Archive</small></div>
      <h1>Deconstructing cinema with artificial intelligence</h1>
      <p>Craft-level analysis across direction, screenplay, cinematography, sound, editing and theme, written
      by the AI model you choose. Scores are AI assessments, kept separate from your ratings and TMDB's.</p>
    </section>"""), unsafe_allow_html=True)
    with st.container(key="hero_search"):
        with st.form("home_form", border=False):
            c1, c2 = st.columns([5, 1], vertical_alignment="center")
            c1.text_input("Film", key="home_q", max_chars=MAX_QUERY_CHARS, label_visibility="collapsed",
                          placeholder="Enter a film — e.g. Chinatown (1974)")
            go = c2.form_submit_button("Analyse film", type="primary", use_container_width=True)
    if go and st.session_state.get("home_q", "").strip():
        goto("critique", critique_query=st.session_state.home_q.strip())
        st.rerun()
    with st.container(key="chips"):
        cols = st.columns(len(EXAMPLE_FILMS))
        for col, film in zip(cols, EXAMPLE_FILMS):
            col.button(film, key=f"home_chip_{film}", on_click=goto, args=("critique",),
                       kwargs={"critique_query": film})


def _latest(ws):
    ss = st.session_state
    if ss.current is not None:
        return ss.current
    for item in ws.list_latest_analyses():
        try:
            return analysis_from_dict(item["payload"])
        except ValueError:
            continue
    return None


def _dossier(a, ctx) -> None:
    c, m = a.critique, a.meta
    scale = ctx.prefs["score_scale"]
    title = (m.title if m and m.title else c.title) or a.query
    director = (m.director if m and m.director else c.director)
    year = (m.year if m and m.year else c.year)
    runtime = (m.runtime if m and m.runtime else c.runtime)
    genres = list(m.genres) if m and m.genres else [x.strip() for x in c.genre.split(",") if x.strip()]
    chips = "".join(f'<span class="pill wine">{esc(x)}</span>' for x in genres[:3])
    chips += "".join(f'<span class="pill">{esc(x)}</span>' for x in (year, runtime) if x)
    spoiler = ('<span class="pill good">Spoiler-free</span>' if a.spoiler_level == "none"
               else f'<span class="pill warn">{esc(SPOILER_LABELS[a.spoiler_level])} · hidden until you reveal</span>')
    source = "TMDB-verified metadata" if m else "AI-supplied metadata (unverified)"
    scores = scoring.dimension_scores(c)
    pillars = ""
    for i, (key, label) in enumerate(DIMENSIONS, 1):
        d = getattr(c, key)
        v = scores[key]
        width = f"{v * 10:.0f}%" if v is not None else "0%"
        num = f"{fmt_score(v, scale)}<small>/ {scale}</small>" if v is not None else "—<small>not assessed</small>"
        pillars += (f'<div class="pillar"><span>{i:02d} · {esc(scoring.label(key))}</span><b>{num}</b>'
                    f'<div class="trk" role="img" aria-label="{esc(label)} score"><i style="width:{width}"></i></div>'
                    f'<p>{esc(d.summary)}</p></div>')
    overall = scoring.valid_score(c.overall_score)
    tags = "".join(f'<span class="pill">{esc(t)}</span>' for t in c.themes_tags)
    verdict = f'<span class="pill gold">{esc(c.verdict_label)}</span>' if c.verdict_label else ""
    st.markdown(compact(f"""
    <section class="dossier">
      <span class="pill wine">Latest dossier</span>
      <h2>{esc(title)}{f'<span class="by">Directed by {esc(director)}</span>' if director else ''}</h2>
      <div class="bar">{chips}{spoiler}<span class="pill">{esc(source)}</span></div>
      <div class="lbl">Craft scorecard · AI assessment (subjective)</div>
      <div class="pillars">{pillars}</div>
      <div class="consensus">
        <div class="big"><span>AI verdict score</span><b>{fmt_score(overall, scale)}</b>{verdict}</div>
        <div class="txt"><h5>{esc(c.pull_quote or 'Verdict')}</h5><p>{esc(c.verdict_text)}</p>
        <div class="bar">{tags}</div></div>
      </div>
    </section>"""), unsafe_allow_html=True)
    b1, b2, b3 = st.columns([1, 1, 4])
    if b1.button("Open full critique", key="home_open", type="primary"):
        st.session_state.current = a
        goto("critique")
        st.rerun()
    b2.button("Graph view", key="home_graph", on_click=goto, args=("graph",))


def _tiles(ctx) -> None:
    ws = ctx.ws
    ss = st.session_state
    cols = st.columns(4)
    # Battles
    b = ss.battle
    if b is not None:
        ta, tb = b.a.critique.title or b.a.query, b.b.critique.title or b.b.query
        body = (f"<h4>{esc(ta)} vs {esc(tb)}</h4><p>Weighted {scoring.fmt(b.comparison.overall_a)} vs "
                f"{scoring.fmt(b.comparison.overall_b)} (/10) · {esc(b.comparison.leader.replace('_', ' '))}</p>")
    else:
        body = "<h4>Head-to-head</h4><p>Compare two films across eight craft categories with a transparent tally.</p>"
    with cols[0]:
        st.markdown(f'<div class="tile"><span class="pill gold">Movie Battles</span>{body}</div>', unsafe_allow_html=True)
        st.button("Open battles", key="home_t1", on_click=goto, args=("battles",))
    # Ask
    hist = [m for msgs in ss.get("ask_hist", {}).values() for m in msgs]
    if hist:
        last = hist[-1]
        body = f"<h4>Conversation</h4><p>Last {esc(last[0])} message: {esc(last[1][:140])}…</p>"
    else:
        body = "<h4>Ask the Critic</h4><p>Ask about craft, context or what to watch next, grounded in your analyses.</p>"
    with cols[1]:
        st.markdown(f'<div class="tile"><span class="pill gold">Ask the Critic</span>{body}</div>', unsafe_allow_html=True)
        st.button("Start a chat", key="home_t2", on_click=goto, args=("ask",))
    # Graph
    nodes = g.nodes_from_data(ws.list_archive(), ws.list_latest_analyses())
    graph = g.build_graph(nodes)
    if len(nodes) >= 2:
        body = (f"<h4>Relational web</h4><p>{graph.number_of_nodes()} films · {graph.number_of_edges()} connections "
                "found from shared directors, cast, franchises, genres and AI-tagged themes.</p>")
    else:
        body = "<h4>Relational web</h4><p>Save or analyse at least two films to see how they connect.</p>"
    with cols[2]:
        st.markdown(f'<div class="tile"><span class="pill gold">Film Intelligence Graph</span>{body}</div>',
                    unsafe_allow_html=True)
        st.button("Open graph", key="home_t3", on_click=goto, args=("graph",))
    # Telemetry (real session numbers only)
    runs, events = ws.recent_runs(), ws.usage_events()
    durs = [r["duration_s"] for r in runs if r["status"] in ("completed", "partial")]
    ok = sum(e["ok"] for e in events)
    cache = metadata.cache_stats()
    lookups = cache["details_hits"] + cache["details_misses"]
    stats = (f'<div class="stats2"><div><span>AI requests</span><b>{len(events)}</b></div>'
             f'<div><span>Avg run</span><b>{fmt_dur(sum(durs) / len(durs)) if durs else "—"}</b></div>'
             f'<div><span>Succeeded</span><b>{ok}/{len(events)}</b></div>'
             f'<div><span>Meta cache hits</span><b>{cache["details_hits"]}/{lookups}</b></div></div>'
             if events or lookups else "<p>No activity in this session yet.</p>")
    with cols[3]:
        st.markdown(f'<div class="tile"><span class="pill gold">Pipeline telemetry</span><h4>This session</h4>{stats}'
                    '<div class="src">Source: local request counts, not provider billing.</div></div>',
                    unsafe_allow_html=True)
        st.button("Open monitor", key="home_t4", on_click=goto, args=("pipeline",))


def _recent(ws, scale: int) -> None:
    items = ws.list_latest_analyses()[:8]
    st.markdown('<div class="lbl" style="margin-top:28px;font:700 11px Inter;letter-spacing:.08em;text-transform:uppercase;'
                'color:#888894">Recent dossiers in this session</div>', unsafe_allow_html=True)
    if not items:
        st.info("No dossiers yet. Analyse a film above and it will appear here. Data lives in this session; "
                "download a backup from the sidebar to keep it.", icon=":material/movie:")
        return
    rows, opts = "", {}
    for it in items:
        try:
            a = analysis_from_dict(it["payload"])
        except ValueError:
            continue
        c, m = a.critique, a.meta
        sc = scoring.dimension_scores(c)
        title = c.title or a.query
        opts[it["film_key"]] = (title, a)
        rows += (f"<tr><td>{esc(title)}{f' ({esc(c.year)})' if c.year else ''}</td>"
                 f"<td>{esc((m.director if m and m.director else c.director) or '—')}</td>"
                 f"<td>{esc(c.genre.split(',')[0] if c.genre else '—')}</td>"
                 f"<td>{scoring.fmt(sc['direction'], scale)}</td><td>{scoring.fmt(sc['screenplay'], scale)}</td>"
                 f"<td>{scoring.fmt(sc['cinematography'], scale)}</td>"
                 f"<td class='num'>{fmt_score(c.overall_score, scale)}</td></tr>")
    st.markdown(compact(f'<div class="tscroll"><table class="ntable"><thead><tr><th>Film</th><th>Director</th><th>Genre</th>'
                        f'<th>Direction</th><th>Screenplay</th><th>Cinematography</th><th>AI verdict</th></tr></thead>'
                        f'<tbody>{rows}</tbody></table></div>'), unsafe_allow_html=True)
    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    pick = c1.selectbox("Open a saved dossier", list(opts), format_func=lambda k: opts[k][0], key="home_pick")
    if c2.button("Open", key="home_pick_go") and pick:
        st.session_state.current = opts[pick][1]
        goto("critique")
        st.rerun()


def render() -> None:
    ctx = get_ctx()
    _hero()
    a = _latest(ctx.ws)
    if a is not None:
        _dossier(a, ctx)
    else:
        st.markdown(compact('<section class="dossier"><span class="pill wine">Latest dossier</span>'
                            '<h2>No analysis yet</h2><p style="color:#B0ADB6;margin-top:8px">Enter a film above. '
                            'Add an AI provider key first in AI Control Center → API Keys.</p></section>'),
                    unsafe_allow_html=True)
        if not any(ctx.keys.values()):
            st.button("Set up AI provider", key="home_setup", on_click=goto, args=("control",), type="primary")
    st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
    _tiles(ctx)
    _recent(ctx.ws, ctx.prefs["score_scale"])
