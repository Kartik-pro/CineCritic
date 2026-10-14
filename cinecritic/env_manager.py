"""Deployment-level secrets: environment variables, .env and (via a registered source) st.secrets.

CineCritic never writes keys to disk. Users may paste a key into the AI Control Center; it
lives only in that browser session's server-side memory. Deployment keys come from Streamlit
Secrets or environment variables, which this module reads (read-only).
"""
from __future__ import annotations

import os
from typing import Callable

from dotenv import load_dotenv

from .config import ENV_PATH

_SOURCES: list[Callable[[str], str]] = []


def load_env() -> None:
    load_dotenv(ENV_PATH)


def register_secret_source(fn: Callable[[str], str]) -> None:
    """Add a lookup (e.g. Streamlit secrets). Idempotent per function object."""
    if fn not in _SOURCES:
        _SOURCES.append(fn)


def get_server_key(name: str) -> str:
    """Environment variable first, then registered sources. Returns '' when absent."""
    value = os.getenv(name, "").strip()
    if value:
        return value
    for source in _SOURCES:
        try:
            value = (source(name) or "").strip()
        except Exception:  # a broken secrets file must never crash the app
            value = ""
        if value:
            return value
    return ""
