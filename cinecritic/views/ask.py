"""Intelligence › Ask the Critic."""
from __future__ import annotations

import streamlit as st

from .. import spoilers
from ..features.ask import MAX_QUESTION, archive_context, ask_critic, film_context
from ..features.serialize import analysis_from_dict
from ..pipeline import PipelineRun
from ..ui.common import header, show_error
from ..ui.live import run_live
from ..ui.runtime import get_ctx
from ..ui.state import workspace


def render() -> None:
    ctx = get_ctx()
    ws = workspace()
    ss = st.session_state
    header("Ask the Critic", "A film-savvy assistant grounded in your analyses. Opinions are labelled as opinions.")
    latest = {i["film_key"]: i for i in ws.list_latest_analyses()}
    titles = {k: ((i["payload"].get("critique") or {}).get("title") or k) for k, i in latest.items()}
    options = [""] + list(latest)
    if ss.ask_film not in options:
        ss.ask_film = ""
    c1, c2, c3 = st.columns([3, 2, 2])
    film = c1.selectbox("Discuss", options, key="ask_film", format_func=lambda k: titles.get(k, "General film talk"))
    levels = spoilers.LEVELS
    level = c2.selectbox("Spoilers", levels, index=levels.index(ctx.level), format_func=lambda x: spoilers.LABELS[x],
                         key="ask_level")
    use_archive = c3.checkbox("Share my archive as context", value=False, key="ask_archive",
                              help="Sends titles, status and ratings of up to 25 saved films to the model.")
    if not latest:
        st.caption("Tip: analyse a film first to ground the conversation in its scorecards.")

    hist = ss.setdefault("ask_hist", {})
    if film not in hist:
        hist[film] = [(m["role"], m["content"]) for m in ws.list_chats(film)] if ctx.prefs["save_chats"] else []
    msgs = hist[film]
    for role, text in msgs:
        with st.chat_message(role):
            st.write(text)

    question = st.chat_input("Ask about a film, a director, or what to watch next…", max_chars=MAX_QUESTION)
    question = question or ss.pop("ask_starter", None)
    if ss.get("ask_confirm") == film and msgs:
        st.warning("Clear this conversation? This cannot be undone.")
        y, n = st.columns(2)
        if y.button("Yes, clear", key="ask_clear_yes", type="primary"):
            hist[film] = []
            ws.clear_chats(film)
            ss.ask_confirm = None
            st.rerun()
        if n.button("Cancel", key="ask_clear_no"):
            ss.ask_confirm = None
            st.rerun()
    elif msgs and st.button("Clear conversation", key="ask_clear", icon=":material/delete:"):
        ss.ask_confirm = film
        st.rerun()
    if not msgs:
        st.caption("Starter ideas:")
        starters = ["What makes this film's cinematography distinctive?", "Which films pair well with this one?",
                    "Explain the director's style without spoilers."]
        cols = st.columns(len(starters))
        for i, (col, text) in enumerate(zip(cols, starters)):
            if col.button(text, key=f"ask_starter_{i}"):
                ss.ask_starter = text
                st.rerun()
    if not question:
        return
    analysis = None
    if film:
        try:
            analysis = analysis_from_dict(latest[film]["payload"])
        except ValueError:
            st.warning("The saved analysis could not be read; answering without it.")
    context = film_context(analysis, level)
    if use_archive:
        context = (context + "\n\n" + archive_context(ws.list_archive())).strip()
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        run = PipelineRun(question[:60], ctx.gateway.label("ask"), kind="ask")
        slot = st.empty()
        history = list(msgs)
        result, err = run_live(run, lambda: ask_critic(ctx.gateway, question, history, context=context, level=level,
                                                       length=ctx.prefs["response_length"],
                                                       language=ctx.prefs["language"], run=run,
                                                       secrets=ctx.secrets), secrets=ctx.secrets, slot=slot)
        if err:
            show_error(err, run=run, key="ask_err")
            return
        answer, removed = result
        slot.empty()
        st.write(answer)
        with st.expander("Copy response"):
            st.code(answer, language=None, wrap_lines=True)
        if removed:
            st.caption(f"{removed} sentence(s) removed by the spoiler filter.")
    msgs += [("user", question), ("assistant", answer)]
    if ctx.prefs["save_chats"]:
        ws.add_chat(film, "user", question)
        ws.add_chat(film, "assistant", answer)
