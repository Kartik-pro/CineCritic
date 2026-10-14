"""CineCritic — Streamlit entry point.  Run with:  streamlit run app.py

Deploys on Streamlit Community Cloud with no database: each visitor gets an in-memory workspace
(see cinecritic/storage/workspace.py) that can be downloaded and restored as a JSON backup.
"""
import streamlit as st

st.set_page_config(page_title="CineCritic — Beyond the Screen", page_icon="🎬", layout="wide",
                   initial_sidebar_state="expanded")

from cinecritic.env_manager import load_env, register_secret_source  # noqa: E402
from cinecritic.errors import configure_logging  # noqa: E402

load_env()               # optional local .env (never committed)
configure_logging()      # redacting server-side log handler (idempotent)


def _streamlit_secret(name: str) -> str:
    """Deployment keys from Streamlit Secrets (read-only). Missing secrets file => empty."""
    try:
        value = st.secrets.get(name, "")
    except Exception:
        return ""
    return value if isinstance(value, str) else ""


register_secret_source(_streamlit_secret)

from cinecritic.config import APP_VERSION  # noqa: E402
from cinecritic.ui.components import brand_html, compact, footer_html  # noqa: E402
from cinecritic.ui.runtime import get_ctx  # noqa: E402
from cinecritic.ui.state import init_state, workspace  # noqa: E402
from cinecritic.ui.styles import inject_styles  # noqa: E402
from cinecritic.views import (archive, ask, battles, control, critique, discovery, graph, home, monitor,  # noqa: E402
                              quests, search)

inject_styles()
init_state()

PAGES = {
    "home": st.Page(home.render, title="Cinema Home", icon=":material/home:", url_path="home", default=True),
    "critique": st.Page(critique.render, title="Film Critique", icon=":material/movie:", url_path="film-critique"),
    "discovery": st.Page(discovery.render, title="Film Discovery", icon=":material/explore:", url_path="film-discovery"),
    "search": st.Page(search.render, title="Smart Movie Search", icon=":material/search:", url_path="movie-search"),
    "ask": st.Page(ask.render, title="Ask the Critic", icon=":material/forum:", url_path="ask-the-critic"),
    "graph": st.Page(graph.render, title="Film Intelligence Graph", icon=":material/hub:", url_path="film-graph"),
    "battles": st.Page(battles.render, title="Head-to-Head Movie Battles", icon=":material/compare_arrows:", url_path="battles"),
    "archive": st.Page(archive.render, title="Personal Film Archive", icon=":material/video_library:", url_path="film-archive"),
    "quests": st.Page(quests.render, title="Discovery Quests", icon=":material/flag:", url_path="quests"),
    "control": st.Page(control.render, title="AI Control Center", icon=":material/tune:", url_path="ai-control-center"),
    "pipeline": st.Page(monitor.render_pipeline, title="Pipeline Monitor", icon=":material/account_tree:", url_path="pipeline-monitor"),
    "diagnostics": st.Page(monitor.render_diagnostics, title="Diagnostics", icon=":material/health_and_safety:", url_path="diagnostics"),
    "usage": st.Page(monitor.render_usage, title="API Usage Monitor", icon=":material/monitoring:", url_path="api-usage"),
}
SECTIONS = {
    "CINEMA": ["home", "critique", "discovery", "search"],
    "INTELLIGENCE": ["ask", "graph", "battles"],
    "MY CINEMA": ["archive", "quests"],
    "SYSTEM & AI": ["control", "pipeline", "diagnostics", "usage"],
}
nav = st.navigation({name: [PAGES[i] for i in ids] for name, ids in SECTIONS.items()})

# Buttons cannot call st.switch_page from a callback; they leave a request that is served here.
request = st.session_state.nav_request
if request:
    st.session_state.nav_request = None
    target, payload = request
    st.session_state.handoff = dict(payload or {})
    if target in PAGES and PAGES[target] is not nav:
        st.switch_page(PAGES[target])


def sidebar() -> None:
    ws = workspace()
    with st.sidebar:
        st.markdown(compact(brand_html()), unsafe_allow_html=True)
        st.divider()
        counts = ws.counts()
        st.caption(f"**Session workspace** · {counts['archive']} films · {counts['analyses']} analyses · "
                   f"{counts['quests']} quests")
        st.caption("No database: this data lives only in your current session. Download a backup to keep it.")
        st.download_button("Download backup", ws.export_json(), "cinecritic-backup.json", "application/json",
                           icon=":material/download:", use_container_width=True, key="sb_backup")
        up = st.file_uploader("Restore backup", type=["json"], key="sb_restore", help="A file from “Download backup”.")
        if up is not None and st.session_state.get("_restored") != up.file_id:
            try:
                done = ws.import_data(up.getvalue())
                st.session_state["_restored"] = up.file_id
                st.success(f"Restored {done['archive']} films, {done['analyses']} analyses, {done['quests']} quests.")
            except ValueError as exc:
                st.session_state["_restored"] = up.file_id
                st.error(str(exc))
        if st.button("Clear my workspace", key="sb_clear", icon=":material/delete_sweep:", use_container_width=True):
            st.session_state["_confirm_clear"] = True
        if st.session_state.get("_confirm_clear"):
            st.warning("Delete all archive, analyses, chats, quests and usage history in this session?")
            c1, c2 = st.columns(2)
            if c1.button("Yes, clear", key="sb_clear_yes"):
                ws.clear_all()
                st.session_state["_confirm_clear"] = False
                st.rerun()
            if c2.button("Cancel", key="sb_clear_no"):
                st.session_state["_confirm_clear"] = False
                st.rerun()
        st.caption(f"CineCritic {APP_VERSION}")


sidebar()
nav.run()
st.markdown(compact(footer_html(bool(get_ctx().tmdb_key))), unsafe_allow_html=True)
