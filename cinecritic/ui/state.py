"""Session state and navigation helpers."""
import streamlit as st

REVIEW_PAGE = "🎞️  Review"
RECOMMEND_PAGE = "✨  Recommend"
PAGES = [REVIEW_PAGE, RECOMMEND_PAGE]


def init_state() -> None:
    st.session_state.setdefault("page", REVIEW_PAGE)
    st.session_state.setdefault("movie_input", "")
    st.session_state.setdefault("auto_run", False)
    st.session_state.setdefault("recos", [])


def jump_to_review(title: str) -> None:
    """Button callback: open the Review page and review `title` immediately."""
    st.session_state.page = REVIEW_PAGE
    st.session_state.movie_input = title
    st.session_state.auto_run = True


def consume_auto_run() -> bool:
    run = st.session_state.auto_run
    st.session_state.auto_run = False
    return run
