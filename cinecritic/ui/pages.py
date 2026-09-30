"""The two app pages: Review and Recommend."""
from __future__ import annotations

import streamlit as st

from ..config import MAX_WORDS
from ..llm import MissingAPIKeyError, get_llm
from ..services import recommend_movies, review_movie
from .components import movie_card_html, ticket_html
from .sidebar import Settings
from .state import consume_auto_run, jump_to_review


def _llm_or_stop(settings: Settings):
    try:
        return get_llm(settings.provider, settings.model_name)
    except MissingAPIKeyError as err:
        st.error(str(err))
        st.stop()


def render_review_page(settings: Settings) -> None:
    col_input, col_btn = st.columns([5, 1])
    movie = col_input.text_input(
        "Movie",
        key="movie_input",
        label_visibility="collapsed",
        placeholder="🎬  Enter a movie — Interstellar, Parasite, Dune...",
    )
    clicked = col_btn.button("Review", use_container_width=True)
    auto = consume_auto_run()

    if (clicked or auto) and movie.strip():
        llm = _llm_or_stop(settings)
        with st.spinner("🎞️ Rolling the projector..."):
            try:
                bullets = review_movie(llm, movie.strip())
                st.markdown(ticket_html(movie, bullets, MAX_WORDS), unsafe_allow_html=True)
            except Exception as err:  # surface provider errors in the UI
                st.error(f"Something went wrong: {err}")
    elif clicked:
        st.warning("Enter a movie name first.")


def render_recommend_page(settings: Settings) -> None:
    text = st.text_area(
        "Taste",
        height=100,
        label_visibility="collapsed",
        placeholder=(
            "✨  Tell me a movie you loved, a mood, or a genre...\n"
            'e.g. "I loved Inception" or "cozy comedies for a rainy night"'
        ),
    )
    if st.button("Recommend"):
        if not text.strip():
            st.warning("Describe a movie, mood, or genre first.")
        else:
            llm = _llm_or_stop(settings)
            with st.spinner("🍿 Scanning the archives..."):
                try:
                    st.session_state.recos = recommend_movies(llm, text.strip(), settings.num_recs)
                except Exception as err:
                    st.error(f"Something went wrong: {err}")

    recos = st.session_state.recos
    if not recos:
        return

    st.markdown('<div class="sec">🎟️ NOW SHOWING — PICKED FOR YOU</div>', unsafe_allow_html=True)
    for start in range(0, len(recos), 3):
        for offset, (col, movie) in enumerate(zip(st.columns(3), recos[start : start + 3])):
            with col:
                st.markdown(movie_card_html(movie, start + offset), unsafe_allow_html=True)
                st.button(
                    "Review this →",
                    key=f"review_{start}_{offset}_{movie.title}",
                    on_click=jump_to_review,
                    args=(movie.title,),
                    use_container_width=True,
                )
