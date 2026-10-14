"""Per-browser-session state. Nothing here is shared between visitors and nothing touches disk.

The "workspace" is an in-memory object (see storage/workspace.py): archive, analyses, quests, usage
and preferences live in st.session_state and are lost when the session ends unless the user
downloads a JSON backup from the sidebar.
"""
from __future__ import annotations

import streamlit as st

from ..ai.gateway import CircuitBreaker
from ..storage.workspace import Workspace


def init_state() -> None:
    ss = st.session_state
    ss.setdefault("ws", Workspace())
    ss.setdefault("api_keys", {})        # service label -> key (server-side session memory only)
    ss.setdefault("key_status", {})      # service label -> credentials.StatusRecord
    ss.setdefault("breaker", CircuitBreaker())
    ss.setdefault("nav_request", None)   # (page id, payload) handled by app.py
    ss.setdefault("handoff", {})         # one-shot values passed between pages
    ss.setdefault("revealed", set())     # film keys whose spoiler notes the user chose to reveal
    ss.setdefault("current", None)       # newest Analysis on the Film Critique page
    ss.setdefault("last_run", None)      # newest PipelineRun (also when it failed)
    ss.setdefault("models_found", {})    # provider -> DiscoveryResult
    ss.setdefault("compare_rows", [])
    ss.setdefault("battle", None)
    ss.setdefault("ask_film", "")
    ss.setdefault("disc", {})


def workspace() -> Workspace:
    return st.session_state["ws"]


def goto(page_id: str, **payload) -> None:
    """Button callback: ask app.py to switch page (st.switch_page cannot run inside a callback)."""
    st.session_state.nav_request = (page_id, payload)


def take_handoff(key: str, default=None):
    """Read and clear a one-shot value placed by goto()."""
    return st.session_state.handoff.pop(key, default)
