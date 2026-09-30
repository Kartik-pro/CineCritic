"""Inject the cinema theme (style.css) into the Streamlit page."""
from pathlib import Path

import streamlit as st

CSS_PATH = Path(__file__).with_name("style.css")


def inject_styles() -> None:
    st.markdown(f"<style>{CSS_PATH.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
