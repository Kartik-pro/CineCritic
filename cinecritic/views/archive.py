"""My Cinema › Personal Film Archive (collection, award nights, backup)."""
from __future__ import annotations

import datetime as dt

import streamlit as st

from .. import scoring
from ..config import DIMENSIONS, MAX_ARCHIVE, SHORT_LABELS
from ..features import awards, exports
from ..features.serialize import analysis_from_dict
from ..ui.common import header
from ..ui.components import esc, safe_image_url
from ..ui.runtime import get_ctx
from ..ui.state import goto, workspace

PAGE_SIZE = 12
STATUSES = ("watched", "watching", "planned")


def _entry(e: dict, ws, scale: int) -> None:
    fkey = e["film_key"]
    meta = e.get("meta") or {}
    poster = safe_image_url(meta.get("poster_url", ""))
    label = f"{'★ ' if e['favorite'] else ''}{e['title']} ({e['year'] or '?'}) · {e['status']}" + \
            (f" · {scoring.fmt(e['rating'], scale)}/{scale}" if e["rating"] is not None else "")
    with st.expander(label):
        c1, c2 = st.columns([1, 4])
        if poster:
            c1.image(poster, width=110)
        with c2:
            a1, a2, a3 = st.columns([2, 2, 1])
            status = a1.selectbox("Status", STATUSES, index=STATUSES.index(e["status"]), key=f"ar_s_{fkey}")
            has = a2.checkbox("Rated", value=e["rating"] is not None, key=f"ar_h_{fkey}")
            fav = a3.toggle("Favourite", value=e["favorite"], key=f"ar_f_{fkey}")
            rating = st.slider("My rating (0–10)", 0.0, 10.0, float(e["rating"] if e["rating"] is not None else 7.0),
                               0.5, key=f"ar_r_{fkey}", disabled=not has)
            review = st.text_area("My review", value=e["review"], key=f"ar_rv_{fkey}", max_chars=4000, height=90)
            notes = st.text_area("Private notes", value=e["notes"], key=f"ar_n_{fkey}", max_chars=4000, height=70)
        b1, b2, b3 = st.columns(3)
        if b1.button("Save changes", key=f"ar_sv_{fkey}", type="primary"):
            ws.upsert_archive(fkey, e["title"], status=status, rating=rating if has else None, review=review,
                              notes=notes, favorite=fav)
            st.toast("Saved.")
            st.rerun()
        item = ws.latest_analysis(fkey)
        if item and b2.button("Open analysis", key=f"ar_o_{fkey}"):
            try:
                st.session_state.current = analysis_from_dict(item["payload"])
                goto("critique")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        elif not item:
            b2.button("Analyze", key=f"ar_a_{fkey}", on_click=goto, args=("critique",),
                      kwargs={"critique_query": f"{e['title']} ({e['year']})" if e["year"] else e["title"]})
        if st.session_state.get("ar_confirm") == fkey:
            st.warning(f"Remove “{e['title']}” from your archive? Saved analyses are kept.")
            y, n = st.columns(2)
            if y.button("Yes, remove", key=f"ar_dy_{fkey}", type="primary"):
                ws.delete_archive(fkey)
                st.session_state.ar_confirm = None
                st.rerun()
            if n.button("Cancel", key=f"ar_dn_{fkey}"):
                st.session_state.ar_confirm = None
                st.rerun()
        elif b3.button("Remove", key=f"ar_d_{fkey}"):
            st.session_state.ar_confirm = fkey
            st.rerun()


def _collection(ctx, ws) -> None:
    scale = ctx.prefs["score_scale"]
    c1, c2, c3, c4 = st.columns([2, 2, 1, 2])
    q = c1.text_input("Search", key="ar_q", placeholder="Title, notes or review")
    status = c2.selectbox("Status", ("", *STATUSES), key="ar_status", format_func=lambda x: x.title() or "All")
    fav = c3.checkbox("Favourites", key="ar_fav")
    sort = c4.selectbox("Sort", ("updated", "added", "title", "year", "rating"), key="ar_sort")
    rows = ws.list_archive(status=status or None, favorite=True if fav else None, query=q, sort=sort)
    watched = [r for r in ws.list_archive(status="watched")]
    rated = [r["rating"] for r in watched if r["rating"] is not None]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Films saved", len(ws.archive))
    m2.metric("Watched", len(watched))
    m3.metric("Average rating", f"{scoring.fmt(sum(rated) / len(rated), scale)}/{scale}" if rated else "—")
    m4.metric("Favourites", sum(r["favorite"] for r in ws.list_archive()))
    if not rows:
        st.info("Nothing here yet. Save films from Film Critique, Discovery or Search.")
        return
    pages = max(1, (len(rows) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = st.number_input("Page", 1, pages, 1, key="ar_page") if pages > 1 else 1
    for e in rows[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]:
        _entry(e, ws, scale)
    with st.expander("Add a film manually"):
        with st.form("ar_add", border=False):
            t, y = st.columns([4, 1])
            title = t.text_input("Title", max_chars=200)
            year = y.text_input("Year", max_chars=4)
            if st.form_submit_button("Add") and title.strip():
                from ..features.serialize import film_key
                try:
                    ws.upsert_archive(film_key(title.strip()), title.strip(), year=year.strip(), status="planned")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    st.markdown("#### Export your collection")
    allrows = ws.list_archive()
    d1, d2, d3 = st.columns(3)
    d1.download_button("CSV", exports.archive_csv(allrows), "cinecritic-collection.csv", "text/csv",
                       icon=":material/table:", key="ar_csv")
    d2.download_button("JSON", exports.archive_json(allrows), "cinecritic-collection.json", "application/json",
                       icon=":material/data_object:", key="ar_json")
    try:
        d3.download_button("PDF", exports.collection_pdf(allrows), "cinecritic-collection.pdf", "application/pdf",
                           icon=":material/picture_as_pdf:", key="ar_pdf")
    except Exception as exc:
        d3.caption(f"PDF unavailable: {getattr(exc, 'message', type(exc).__name__)}")


def _awards(ctx, ws) -> None:
    st.caption(awards.LABEL)
    films: dict[str, tuple[str, dict]] = {}
    for item in ws.list_latest_analyses():
        try:
            a = analysis_from_dict(item["payload"])
        except ValueError:
            continue
        films[item["film_key"]] = (a.critique.title or a.query, scoring.dimension_scores(a.critique))
    if len(films) < awards.MIN_NOMINEES:
        st.info("Analyse at least two films to hold an award night.")
        return
    chosen = st.multiselect("Nominated films", list(films), default=list(films)[:12], key="aw_films",
                            format_func=lambda k: films[k][0])
    cats = awards.default_categories()
    with st.expander("Add a custom category"):
        n = st.text_input("Category name", key="aw_cname", max_chars=60)
        dims = st.multiselect("Craft dimensions to average", list(SHORT_LABELS), key="aw_cdims",
                              format_func=SHORT_LABELS.get)
        if st.button("Add category", key="aw_cadd"):
            try:
                st.session_state.setdefault("aw_custom", []).append(awards.custom_category(n, dims))
            except ValueError as exc:
                st.error(str(exc))
    cats += st.session_state.get("aw_custom", [])
    picked = st.multiselect("Categories", [c.id for c in cats], default=[c.id for c in cats if not c.custom] +
                            [c.id for c in cats if c.custom], key="aw_cats",
                            format_func=lambda i: next(c.title for c in cats if c.id == i))
    overrides = {}
    with st.expander("Choose a winner yourself (optional)"):
        for c in (c for c in cats if c.id in picked):
            sel = st.selectbox(c.title, [""] + chosen, key=f"aw_o_{c.id}",
                               format_func=lambda k: films[k][0] if k else "Let CineCritic decide (score-based)")
            if sel:
                overrides[c.id] = sel
    results = awards.run_awards({k: films[k] for k in chosen}, [c for c in cats if c.id in picked],
                                ctx.prefs["weights"], overrides)
    scale = ctx.prefs["score_scale"]
    for r in results:
        with st.container(border=True):
            icon = {"winner": "🏆", "tie": "🤝", "inconclusive": "❔"}[r.status]
            names = " & ".join(w.title for w in r.winners) or "No winner"
            st.markdown(f"**{icon} {esc(r.category.title)} — {esc(names)}**")
            st.caption(f"{r.selected_by} · {r.explanation}")
    if results:
        try:
            st.download_button("Download awards night (PDF)", exports.awards_pdf(results, scale=scale),
                               "cinecritic-awards.pdf", "application/pdf", icon=":material/picture_as_pdf:",
                               key="aw_pdf")
        except Exception as exc:
            st.caption(f"PDF unavailable: {getattr(exc, 'message', type(exc).__name__)}")


def render() -> None:
    ctx = get_ctx()
    ws = ctx.ws
    header("Personal Film Archive", "Your collection, ratings and reviews. Kept in this session; download a backup to keep it.")
    t1, t2 = st.tabs(["Collection", "Award nights"])
    with t1:
        _collection(ctx, ws)
    with t2:
        _awards(ctx, ws)
