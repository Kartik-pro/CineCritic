"""CineCritic — Streamlit entry point.  Run with:  streamlit run app.py"""
import streamlit as st

from cinecritic.env_manager import load_env

load_env()  # must run before any provider SDK reads its API key

from cinecritic.ui.components import hero_html  # noqa: E402
from cinecritic.ui.pages import render_recommend_page, render_review_page  # noqa: E402
from cinecritic.ui.sidebar import render_sidebar  # noqa: E402
from cinecritic.ui.state import PAGES, REVIEW_PAGE, init_state  # noqa: E402
from cinecritic.ui.styles import inject_styles  # noqa: E402

st.set_page_config(page_title="CineCritic", page_icon="🎬", layout="wide")
inject_styles()
init_state()

settings = render_sidebar()

st.markdown(hero_html(), unsafe_allow_html=True)
st.radio("Navigate", PAGES, horizontal=True, key="page", label_visibility="collapsed")
st.write("")

if st.session_state.page == REVIEW_PAGE:
    render_review_page(settings)
else:
    render_recommend_page(settings)
