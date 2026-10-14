"""Intelligence › Film Intelligence Graph."""
from __future__ import annotations

import streamlit as st

from ..features import graph as g
from ..ui.common import header
from ..ui.state import goto, workspace


def render() -> None:
    ws = workspace()
    header("Film Intelligence Graph", "How the films you have saved or analysed connect. Every link states its reason.")
    nodes = g.nodes_from_data(ws.list_archive(), ws.list_latest_analyses())
    if len(nodes) < 2:
        st.info("The graph appears once you have at least two films in your archive or analyses.")
        st.button("Analyze a film", on_click=goto, args=("critique",))
        return
    c1, c2, c3 = st.columns([3, 1, 1])
    kinds = c1.multiselect("Connection types", list(g.KINDS), default=list(g.KINDS), format_func=g.KINDS.get,
                           key="graph_kinds")
    min_genres = c2.slider("Min shared genres", 1, 4, 2, key="graph_mg")
    maximum = c3.slider("Max films shown", 10, g.MAX_NODES, g.MAX_NODES, key="graph_max")
    graph = g.build_graph(nodes, set(kinds), min_genres)
    shown, hidden = g.limit_nodes(graph, maximum)
    options = sorted(shown.nodes, key=lambda k: shown.nodes[k]["node"].label)
    selected = st.selectbox("Focus on a film", [""] + options, key="graph_sel",
                            format_func=lambda k: shown.nodes[k]["node"].label if k else "None")
    if shown.number_of_edges() == 0:
        st.info("No connections match these settings. Add more films or enable more connection types.")
    else:
        try:
            st.graphviz_chart(g.to_dot(shown, selected or None), use_container_width=True)
        except Exception:
            st.warning("The graph could not be drawn here; the table below lists the same connections.")
        st.caption("Solid links come from verified TMDB data; dashed links rely only on AI-supplied credits or tags. "
                   f"{shown.number_of_nodes()} films shown" + (f", {hidden} unconnected or lower-ranked hidden." if hidden else "."))
    st.markdown('<span class="pill">Legend</span> ' + " ".join(
        f'<span class="pill" style="border-color:{g._COLORS[k]};color:{g._COLORS[k]}">{label.split(" (")[0]}</span>'
        for k, label in g.KINDS.items()), unsafe_allow_html=True)
    if shown.number_of_edges():
        with st.expander("Connections as a table (also the mobile-friendly view)"):
            st.dataframe([{"Film A": shown.nodes[u]["node"].label, "Film B": shown.nodes[v]["node"].label,
                           "Why": "; ".join(r.text for r in d["reasons"]),
                           "Basis": "verified (TMDB)" if all(r.verified for r in d["reasons"]) else "includes AI-inferred"}
                          for u, v, d in shown.edges(data=True)], hide_index=True, use_container_width=True)
    if selected:
        st.markdown("#### Why these films connect")
        rel = g.relations_for(shown, selected)
        if not rel:
            st.write("No connections for this film under the current settings.")
        for node, reasons in rel:
            with st.container(border=True):
                st.markdown(f"**{node.label}**")
                for r in reasons:
                    st.write(f"• {r.text}" + ("" if r.verified else " _(unverified)_"))
