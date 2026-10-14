"""Cinema › Smart Movie Search."""
from __future__ import annotations

import streamlit as st

from .. import metadata
from ..errors import AppError, classify
from ..features.quests import LANGUAGE_NAMES
from ..services import suggest_titles
from ..ui.common import candidate_card, header, need_tmdb, show_error
from ..ui.runtime import get_ctx


def render() -> None:
    ctx = get_ctx()
    header("Smart Movie Search", "Search TMDB by title, refine the results, or describe a film you can't name.")
    if not need_tmdb(ctx, "Movie search"):
        return
    try:
        genres = metadata.genre_map(ctx.tmdb_key)
    except AppError:
        genres = {}
    tab1, tab2 = st.tabs(["By title", "Describe a film"])
    with tab1:
        with st.form("search_form", border=False):
            c1, c2, c3 = st.columns([4, 1, 1], vertical_alignment="bottom")
            title = c1.text_input("Title", key="search_title", max_chars=120, placeholder="Heat")
            year = c2.text_input("Year", key="search_year", max_chars=4)
            go = c3.form_submit_button("Search", type="primary", use_container_width=True)
        if go and title.strip():
            st.session_state.search_state = (title.strip(), year.strip() if year.strip().isdigit() else "")
            st.session_state.search_page_n = 1
        state = st.session_state.get("search_state")
        if state:
            page_n = st.number_input("Page", 1, 20, key="search_page_n")
            try:
                with st.spinner("Searching TMDB…"):
                    page = metadata.search_page(state[0], ctx.tmdb_key, int(page_n), state[1])
            except AppError as err:
                show_error(err, key="search_err")
                return
            f1, f2, f3, f4 = st.columns(4)
            picked = f1.multiselect("Genre", sorted(genres.values()), key="sf_genres")
            by_name = {v: k for k, v in genres.items()}
            min_rating = f2.slider("Min TMDB rating", 0.0, 9.0, 0.0, 0.5, key="sf_rating")
            lang = f3.selectbox("Language", [""] + list(LANGUAGE_NAMES), key="sf_lang",
                                format_func=lambda x: LANGUAGE_NAMES.get(x, "Any"))
            sort = f4.selectbox("Sort", ("Relevance", "Popularity", "Rating", "Newest", "Oldest", "Title"), key="sf_sort")
            items = metadata.filter_sort(page.items, genre_ids=tuple(by_name[g] for g in picked), min_rating=min_rating,
                                         language=lang, sort=sort)
            st.caption(f"{page.total_results:,} matches for “{state[0]}” · showing {len(items)} on this page after filters")
            if not items:
                st.info("Nothing matches those filters on this page. Loosen them or try another page.")
            for start in range(0, len(items), 4):
                cols = st.columns(4)
                for col, c in zip(cols, items[start:start + 4]):
                    with col:
                        candidate_card(c, f"s_{c.id}", genres)
    with tab2:
        st.write("Can't remember the title? Describe the plot, scene or actors. The AI suggests titles, and only "
                 "films that TMDB confirms are shown.")
        text = st.text_area("Describe the film", key="search_desc", max_chars=300, height=90,
                            placeholder="A thief enters people's dreams to plant an idea")
        if st.button("Find it", key="search_desc_go", type="primary", icon=":material/psychology:") and text.strip():
            try:
                with st.spinner("Thinking…"):
                    st.session_state.search_found = suggest_titles(ctx.gateway, text, ctx.tmdb_key,
                                                                   secrets=ctx.secrets)
            except Exception as exc:
                show_error(exc if isinstance(exc, AppError) else classify(exc, source="ai", secrets=ctx.secrets),
                           key="search_ai_err")
        found = st.session_state.get("search_found") or []
        if st.session_state.get("search_found") == []:
            st.info("No verified match. Try adding more detail.")
        for start in range(0, len(found), 4):
            cols = st.columns(4)
            for col, c in zip(cols, found[start:start + 4]):
                with col:
                    candidate_card(c, f"sd_{c.id}", genres)
