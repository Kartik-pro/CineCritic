"""Film Intelligence Graph: relationships among films the user has analysed or archived.

Relationships come from data the app really has:
* verified  - director, shared cast, franchise/collection and genres from TMDB metadata;
* inferred  - shared thematic tags written by the AI in analyses (always labelled as AI-inferred);
* AI-supplied credits (no TMDB record) are used for directors but flagged as unverified.
Nothing is invented: a pair with no supported reason has no edge.
"""
from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

KINDS = {"director": "Same director", "actor": "Shared cast", "franchise": "Same franchise",
         "genre": "Shared genres", "theme": "Shared themes (AI-inferred)"}
_COLORS = {"franchise": "#B4415A", "director": "#C6A15B", "actor": "#34D399", "genre": "#888894", "theme": "#60A5FA"}
MAX_NODES = 60


@dataclass(frozen=True)
class Node:
    key: str
    title: str
    year: str = ""
    tmdb_id: int = 0
    genres: tuple[str, ...] = ()
    director: str = ""
    cast: tuple[str, ...] = ()
    collection_id: int = 0
    collection_name: str = ""
    themes: tuple[str, ...] = ()
    verified: bool = False          # metadata came from TMDB (not AI-supplied)
    analysed: bool = False

    @property
    def label(self) -> str:
        return f"{self.title} ({self.year})" if self.year else self.title


@dataclass(frozen=True)
class Reason:
    kind: str
    text: str
    verified: bool


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


def nodes_from_data(archive: list[dict], analyses: list[dict]) -> list[Node]:
    """Merge archive snapshots and stored analyses into nodes (keyed by film key)."""
    by_key: dict[str, dict] = {}
    for e in archive:
        m = e.get("meta") or {}
        by_key[e["film_key"]] = {
            "title": e["title"], "year": e.get("year", ""), "tmdb_id": int(m.get("tmdb_id") or 0),
            "genres": m.get("genres") or [], "director": m.get("director") or "",
            "cast": [p[0] for p in (m.get("cast") or []) if p],
            "collection_id": int(m.get("collection_id") or 0), "collection_name": m.get("collection_name") or "",
            "themes": m.get("themes") or [], "analysed": False}
    for item in analyses:
        payload = item.get("payload") or {}
        c = payload.get("critique") or {}
        meta = payload.get("meta") or {}
        key = item["film_key"]
        row = by_key.setdefault(key, {"title": "", "year": "", "tmdb_id": 0, "genres": [], "director": "", "cast": [],
                                      "collection_id": 0, "collection_name": "", "themes": [], "analysed": False})
        row["title"] = row["title"] or meta.get("title") or c.get("title") or ""
        row["year"] = row["year"] or meta.get("year") or c.get("year") or ""
        row["tmdb_id"] = row["tmdb_id"] or int(meta.get("tmdb_id") or 0)
        row["genres"] = row["genres"] or list(meta.get("genres") or []) or [g.strip() for g in str(c.get("genre", "")).split(",") if g.strip()]
        row["director"] = row["director"] or meta.get("director") or c.get("director") or ""
        row["cast"] = row["cast"] or [p[0] for p in (meta.get("cast") or []) if p]
        row["collection_id"] = row["collection_id"] or int(meta.get("collection_id") or 0)
        row["collection_name"] = row["collection_name"] or meta.get("collection_name") or ""
        row["themes"] = list(c.get("themes_tags") or row["themes"])
        row["analysed"] = True
    nodes = []
    for key, r in by_key.items():
        if not r["title"]:
            continue
        nodes.append(Node(key, r["title"], str(r["year"] or ""), r["tmdb_id"], tuple(r["genres"]), r["director"],
                          tuple(r["cast"]), r["collection_id"], r["collection_name"],
                          tuple(t for t in r["themes"] if t), verified=r["tmdb_id"] > 0, analysed=r["analysed"]))
    return nodes


def reasons_between(a: Node, b: Node, min_genres: int = 2) -> list[Reason]:
    out: list[Reason] = []
    if a.director and _norm(a.director) == _norm(b.director):
        out.append(Reason("director", f"Both directed by {a.director}" +
                          ("" if a.verified and b.verified else " (credit supplied by the AI, not TMDB)"),
                          a.verified and b.verified))
    shared_cast = sorted({_norm(n): n for n in a.cast}.keys() & {_norm(n) for n in b.cast})
    if shared_cast:
        names = [n for n in a.cast if _norm(n) in shared_cast]
        out.append(Reason("actor", "Shared cast: " + ", ".join(names[:4]), True))
    if a.collection_id and a.collection_id == b.collection_id:
        out.append(Reason("franchise", f"Both belong to “{a.collection_name or 'the same collection'}”", True))
    shared_genres = sorted({g.lower() for g in a.genres} & {g.lower() for g in b.genres})
    if len(shared_genres) >= min_genres:
        out.append(Reason("genre", "Shared genres: " + ", ".join(g.title() for g in shared_genres),
                          a.verified and b.verified))
    shared_themes = sorted({t.lower() for t in a.themes} & {t.lower() for t in b.themes})
    if shared_themes:
        out.append(Reason("theme", "Both tagged by the AI with: " + ", ".join(shared_themes) + " (AI interpretation)",
                          False))
    return out


def build_graph(nodes: list[Node], kinds: set[str] | None = None, min_genres: int = 2) -> nx.Graph:
    """Graph whose edges carry `reasons`. Only reasons of the selected kinds are kept."""
    kinds = set(kinds or KINDS)
    g = nx.Graph()
    for n in nodes:
        g.add_node(n.key, node=n)
    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            reasons = [r for r in reasons_between(a, b, min_genres) if r.kind in kinds]
            if reasons:
                g.add_edge(a.key, b.key, reasons=reasons)
    return g


def limit_nodes(g: nx.Graph, maximum: int = MAX_NODES, drop_isolated: bool = True) -> tuple[nx.Graph, int]:
    """Keep the best-connected nodes so the picture stays readable. Returns (graph, hidden_count)."""
    h = g.copy()
    if drop_isolated:
        h.remove_nodes_from([n for n, d in dict(h.degree()).items() if d == 0])
    hidden = g.number_of_nodes() - h.number_of_nodes()
    if h.number_of_nodes() > maximum:
        keep = {n for n, _ in sorted(h.degree(), key=lambda x: (-x[1], x[0]))[:maximum]}
        hidden += h.number_of_nodes() - len(keep)
        h = h.subgraph(keep).copy()
    return h, hidden


def _q(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def to_dot(g: nx.Graph, selected: str | None = None) -> str:
    """Graphviz DOT for st.graphviz_chart. Dashed edges are AI-inferred only."""
    lines = ['graph G {', 'layout=neato; overlap=false; splines=true; bgcolor="transparent";',
             'node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11, fontcolor="#EDE8DF", '
             'fillcolor="#202027", color="#34343D"];', 'edge [fontname="Helvetica", fontsize=9, fontcolor="#B0ADB6"];']
    for key, data in g.nodes(data=True):
        n: Node = data["node"]
        extra = ', color="#E0C17E", penwidth=2' if key == selected else ""
        lines.append(f'"{_q(key)}" [label="{_q(n.label)}"{extra}];')
    for u, v, data in g.edges(data=True):
        reasons: list[Reason] = data["reasons"]
        kinds = [r.kind for r in reasons]
        top = min(kinds, key=list(_COLORS).index) if kinds else "genre"
        style = "dashed" if all(not r.verified for r in reasons) else "solid"
        label = " + ".join(sorted({KINDS[k].split(" (")[0].lower() for k in kinds}))
        lines.append(f'"{_q(u)}" -- "{_q(v)}" [color="{_COLORS[top]}", style={style}, label="{_q(label)}"];')
    lines.append("}")
    return "\n".join(lines)


def relations_for(g: nx.Graph, key: str) -> list[tuple[Node, list[Reason]]]:
    if key not in g:
        return []
    out = [(g.nodes[o]["node"], g.edges[key, o]["reasons"]) for o in g.neighbors(key)]
    return sorted(out, key=lambda x: -len(x[1]))
