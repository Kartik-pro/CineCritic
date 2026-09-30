"""Sidebar: provider, model, API key management and recommendation count."""
from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from ..config import PROVIDERS, Provider
from ..env_manager import get_api_key, save_api_key


@dataclass
class Settings:
    provider: Provider
    model_name: str
    num_recs: int


def render_sidebar() -> Settings:
    with st.sidebar:
        st.markdown("### 🔑 Model & API Key")
        provider = PROVIDERS[st.selectbox("Provider", list(PROVIDERS))]
        model_name = st.text_input("Model", value=provider.default_model)

        current = get_api_key(provider.env_var)
        if current:
            st.markdown(
                f'<div class="status ok">✔ {provider.env_var} loaded (…{current[-4:]})</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="status no">✖ {provider.env_var} not set</div>',
                unsafe_allow_html=True,
            )

        new_key = st.text_input("API key", type="password", placeholder="Paste your key here")
        if st.button("💾 Save to .env", use_container_width=True):
            if new_key.strip():
                save_api_key(provider.env_var, new_key)
                st.rerun()
            else:
                st.warning("Enter a key first.")

        st.markdown("---")
        num_recs = st.slider("Recommendations", 3, 9, 6, step=3)
        st.caption("Keep .env out of Git (it is already in .gitignore).")

    return Settings(provider, model_name, num_recs)
