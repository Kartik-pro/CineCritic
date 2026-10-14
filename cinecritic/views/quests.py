"""My Cinema › Discovery Quests."""
from __future__ import annotations

import streamlit as st

from .. import metadata
from ..errors import AppError, classify
from ..features import quests as q
from ..ui.common import candidate_card, header, need_tmdb, show_error
from ..ui.runtime import get_ctx


def _create(ctx) -> None:
    ws = ctx.ws
    with st.expander("Start a new quest", expanded=not ws.quests):
        kind = st.selectbox("Quest type", list(q.KINDS), format_func=q.KINDS.get, key="qu_kind")
        needs_tmdb = kind in ("director", "collection")
        genres = {}
        if ctx.tmdb_key:
            try:
                genres = metadata.genre_map(ctx.tmdb_key)
            except AppError:
                pass
        spec = None
        error = None
        try:
            if kind == "genre":
                genre = st.selectbox("Genre", sorted(genres.values()) or ["Drama", "Comedy", "Thriller", "Horror",
                                                                         "Science Fiction", "Animation"], key="qu_genre")
                target = st.slider("Films to watch", 2, 10, 5, key="qu_gt")
                spec = lambda: q.genre_quest(genre, target)
            elif kind == "decades":
                target = st.slider("Decades to cover", 2, 8, 5, key="qu_dt")
                spec = lambda: q.decades_quest(target)
            elif kind == "international":
                target = st.slider("Languages beyond English", 2, 8, 3, key="qu_it")
                spec = lambda: q.international_quest(target)
            elif kind == "director":
                name = st.text_input("Director", key="qu_dir", max_chars=80, placeholder="Denis Villeneuve")
                spec = lambda: q.director_quest(name, ctx.tmdb_key)
            else:
                name = st.text_input("Franchise or collection", key="qu_col", max_chars=80, placeholder="The Dark Knight")
                spec = lambda: q.collection_quest(name, ctx.tmdb_key)
        except Exception as exc:  # defensive: widget construction only
            error = exc
        if needs_tmdb and not need_tmdb(ctx, "This quest type"):
            return
        if error:
            st.error(str(error))
        elif spec and st.button("Create quest", key="qu_create", type="primary"):
            try:
                with st.spinner("Building quest…"):
                    title, params, target = spec()
                ws.create_quest(kind, title, params, target)
                st.rerun()
            except ValueError as exc:
                st.warning(str(exc))
            except AppError as exc:
                show_error(exc, key="qu_err")
            except Exception as exc:
                show_error(classify(exc, source="tmdb", secrets=ctx.secrets), key="qu_err2")


def render() -> None:
    ctx = get_ctx()
    ws = ctx.ws
    header("Discovery Quests", "Goals that grow your taste. Progress counts films marked as watched in your archive.")
    _create(ctx)
    archive = ws.list_archive()
    quests = ws.list_quests()
    if not quests:
        st.info("No quests yet. Create one above.")
        return
    for quest in quests:
        done, target, matched = q.progress(quest, archive)
        if done >= target and not quest["completed_at"]:
            ws.complete_quest(quest["id"])
            quest["completed_at"] = True
        with st.container(border=True):
            st.markdown(f"**{'✅ ' if quest['completed_at'] else ''}{quest['title']}**")
            st.progress(min(1.0, done / target), text=f"{done} of {target}")
            if matched:
                st.caption("Counted: " + ", ".join(matched[:12]))
            c1, c2, c3 = st.columns([1, 1, 3])
            if c1.button("Delete", key=f"qu_del_{quest['id']}"):
                ws.delete_quest(quest["id"])
                st.rerun()
            if not quest["completed_at"] and ctx.tmdb_key:
                if c2.button("Find films", key=f"qu_find_{quest['id']}"):
                    st.session_state.qu_open = quest["id"]
            films = q.remaining_films(quest, archive)
            if films and quest["kind"] in ("director", "collection"):
                c3.caption("Still to watch: " + ", ".join(f"{f['title']} ({f.get('year', '')})" for f in films[:8]))
            if st.session_state.get("qu_open") == quest["id"] and ctx.tmdb_key:
                try:
                    gm = metadata.genre_map(ctx.tmdb_key)
                    genre_ids = {v.lower(): k for k, v in gm.items()}
                    kw = q.discover_kwargs(quest, archive, genre_ids)
                    if kw is None:
                        st.info("No suggestions for this quest right now.")
                    else:
                        page = metadata.discover_page(ctx.tmdb_key, **kw)
                        have = {e["film_key"] for e in archive}
                        items = [c for c in page.items if f"tmdb:{c.id}" not in have][:4]
                        cols = st.columns(4)
                        for col, c in zip(cols, items):
                            with col:
                                candidate_card(c, f"qu_{quest['id']}_{c.id}", gm)
                except AppError as err:
                    show_error(err, key=f"qu_e_{quest['id']}")
