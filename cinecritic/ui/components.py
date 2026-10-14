"""Pure HTML builders for every section of the page. No Streamlit calls in here."""
from __future__ import annotations

import html
import re
from urllib.parse import urlparse

from ..config import DIMENSIONS, MAX_WORDS
from ..schemas import Critique, Dimension, valid_score
from ..errors import CATEGORY_LABELS
from ..pipeline import STATUS_LABELS, PipelineRun, Status
from ..services import Analysis, Reco
from .icons import icon



def esc(text) -> str:
    """HTML-escape and collapse whitespace: a stray blank line from the model would
    otherwise end the raw-HTML block in Streamlit's markdown renderer."""
    return html.escape(re.sub(r"\s+", " ", str(text)).strip())


def compact(markup: str) -> str:
    """Remove inter-tag whitespace so indentation can never become a markdown code block."""
    return re.sub(r">\s*\n\s*<", "><", markup).strip()


POSTER_GRADIENTS = [
    "linear-gradient(160deg,#3a2f17,#17171D)",
    "linear-gradient(160deg,#42131F,#17171D)",
    "linear-gradient(160deg,#202027,#111116)",
    "linear-gradient(160deg,#2c2616,#17171D)",
    "linear-gradient(160deg,#292932,#111116)",
]
_ALLOWED_IMG_HOSTS = {"image.tmdb.org"}


def safe_image_url(url: str) -> str:
    """Only https images from known hosts are ever placed into CSS/HTML."""
    try:
        parsed = urlparse(url or "")
    except ValueError:
        return ""
    if parsed.scheme == "https" and parsed.netloc in _ALLOWED_IMG_HOSTS:
        return html.escape(url, quote=True)
    return ""


def fmt_score(value: float | None, scale: int = 10) -> str:
    """Format a stored 0-10 score on the chosen display scale (10, 5 or 100)."""
    score = valid_score(value)
    if score is None:
        return "—"
    shown = score / 10.0 * scale
    return f"{shown:.0f}" if scale == 100 else f"{shown:.1f}"


def _first(*values: str) -> str:
    return next((v.strip() for v in values if v and v.strip()), "")


# --------------------------------------------------------------------------- chrome
def brand_html() -> str:
    return (
        f'<div class="brand">{icon("film", 22)}'
        '<div><div class="brand-name">CineCritic</div>'
        '<div class="brand-sub">Beyond the screen</div></div></div>'
    )


def hero_html() -> str:
    return """
    <section class="hero">
      <div class="badge">&#9733; AI-powered film intelligence &amp; critique &#9733;</div>
      <h1>Every Film Has a Story.<br><em>Discover What Lies Beneath.</em></h1>
      <p>Deep cinematic analysis across eight craft dimensions &mdash; plot, screenplay,
      direction, performance, cinematography, sound, pacing and theme &mdash; written by the
      AI model of your choice. Enter any feature film.</p>
    </section>"""


def chips_label_html() -> str:
    return '<div class="chips-label">Featured inquiries</div>'


def empty_state_html() -> str:
    return f"""
    <section class="empty">
      <div class="empty-ic">{icon("film", 34)}</div>
      <h2>Your critique will appear here</h2>
      <p>Search a film above, or pick one of the featured inquiries. You will get eight
      scored craft dimensions, strengths and flaws, an editorial verdict and similar films.</p>
    </section>"""


def footer_html(tmdb_used: bool) -> str:
    tmdb = (
        '<p class="tmdb">Film imagery and credits courtesy of TMDB. This product uses the '
        "TMDB API but is not endorsed or certified by TMDB.</p>"
        if tmdb_used
        else ""
    )
    return f"""
    <footer class="foot">
      <div>
        <div class="foot-brand">CineCritic</div>
        <p>AI film criticism with scored craft dimensions. Scores are CineCritic AI
        assessments, not IMDb or audience ratings, and AI can make mistakes.</p>
      </div>
      <div>
        <div class="foot-h">Privacy</div>
        <p>Keys you paste stay in this session&rsquo;s server memory only. They are never
        written to disk, logs or URLs, and are sent only to the provider you chose. Your film data lives in
        this session unless you download a backup.</p>
        {tmdb}
      </div>
    </footer>"""


# --------------------------------------------------------------------------- featured card
def featured_html(a: Analysis, scale: int = 10) -> str:
    c, m = a.critique, a.meta
    title = _first(m.title if m else "", c.title, a.query)
    year = _first(m.year if m else "", c.year)
    runtime = _first(m.runtime if m else "", c.runtime)
    genres = (", ".join(m.genres) if m and m.genres else c.genre).strip()
    verified = bool(m)

    director = _first(m.director if m else "", c.director)
    cinema = _first(m.cinematographer if m else "", c.cinematographer)
    composer = _first(m.composer if m else "", c.composer)
    credits = "".join(
        f'<div><span>{label}</span><b>{esc(value)}</b></div>'
        for label, value in (("Directed by", director), ("Cinematography", cinema), ("Original score", composer))
        if value
    )

    cast_line = (
        '<div class="cast"><span>Cast (TMDB)</span> '
        + esc(" · ".join(n for n, _ in m.cast[:5])) + "</div>"
        if m and m.cast else ""
    )
    rating_chip = (
        f'<span class="meta-chip tmdb" title="Audience average from TMDB, not a CineCritic score">'
        f'TMDB {m.rating:.1f} ({m.votes:,} votes)</span>'
        if m and m.rating else ""
    )
    backdrop = safe_image_url(m.backdrop_url) if m else ""
    bg_style = (
        f"background-image:linear-gradient(180deg,rgba(13,13,16,.25),rgba(13,13,16,.92)),url('{backdrop}')"
        if backdrop
        else "background-image:radial-gradient(ellipse at 70% 20%,rgba(116,31,50,.28),transparent 60%),"
        "linear-gradient(135deg,#202027,#0D0D10)"
    )
    chips = "".join(
        f'<span class="meta-chip">{esc(x)}</span>' for x in (year, runtime) if x
    )
    chips += rating_chip
    if genres:
        chips += f'<span class="meta-text">{esc(genres)}</span>'

    overall = valid_score(c.overall_score)
    score_block = (
        f'<div class="score"><div class="score-ring"><b>{fmt_score(overall, scale)}</b><small>/{scale}</small></div>'
        f'<div><span class="tag-gold">{icon("award", 13)} CineCritic assessment</span>'
        f'<div class="score-sub">AI-generated score</div></div></div>'
        if overall is not None
        else '<div class="score"><div class="score-sub">No overall score available</div></div>'
    )
    source = "Verified credits &amp; imagery: TMDB" if verified else "Credits are AI-supplied and unverified"
    quote = (
        f'<blockquote class="pull">{esc(c.pull_quote)}</blockquote>' if c.pull_quote.strip() else ""
    )
    return f"""
    <section class="featured" aria-label="Featured film">
      <div class="feat-img" style="{bg_style}" role="img" aria-label="Backdrop for {esc(title)}">
        <span class="badge-red">CineCritic analysis</span>
        <div class="feat-body">
          <div class="feat-meta">{chips}</div>
          <h2 class="feat-title">{esc(title)}</h2>
          <div class="credits">{credits}</div>
          {cast_line}
          <div class="feat-src">{source}</div>
        </div>
        {score_block}
      </div>
      {quote}
    </section>"""


# --------------------------------------------------------------------------- critique grid
def _card(key: str, title: str, d: Dimension, scale: int = 10, weight: float | None = None) -> str:
    score = valid_score(d.score)
    bar = (
        f'<div class="bar" role="img" aria-label="{score:.1f} out of 10"><span style="width:{score * 10:.0f}%"></span></div>'
        if score is not None
        else '<div class="bar off"></div>'
    )
    detail = (
        f'<details><summary>Detailed analysis</summary><p class="det">{esc(d.detail)}</p></details>'
        if d.detail.strip()
        else ""
    )
    ref = f'<span class="ref">{esc(d.reference)}</span>' if d.reference.strip() else "<span></span>"
    wt = f'<span class="wt">weight {weight:g}</span>' if weight is not None else ""
    return f"""
    <article class="dim">
      <header><h3>{icon(key)}{esc(title)}</h3><b>{fmt_score(score, scale)}</b></header>
      {bar}
      <p class="sum">{esc(d.summary)}</p>
      {detail}
      <footer>{ref}{wt}</footer>
    </article>"""


def _strengths_card(c: Critique) -> str:
    good = "".join(f"<li>{esc(s)}</li>" for s in c.strengths)
    bad = "".join(f"<li>{esc(s)}</li>" for s in c.flaws)
    return f"""
    <article class="dim sf">
      <header><h3>{icon("scale")}Strengths &amp; Flaws</h3><span class="tag-mini">Synthesis</span></header>
      <div class="sf-good"><h4>{icon("check", 13)} Strengths</h4><ul>{good or "<li>None reported</li>"}</ul></div>
      <div class="sf-bad"><h4>{icon("alert", 13)} Flaws</h4><ul>{bad or "<li>None reported</li>"}</ul></div>
    </article>"""


def critique_grid_html(a: Analysis, scale: int = 10, weights: dict | None = None) -> str:
    c = a.critique
    cards = "".join(_card(key, title, getattr(c, key), scale, (weights or {}).get(key)) for key, title in DIMENSIONS)
    return f"""
    <section id="critique-grid">
      <div class="eyebrow">Decoupled critique analysis</div>
      <h2 class="sec-title">Multi-Parameter Critique Breakdown</h2>
      <div class="grid3">{cards}{_strengths_card(c)}</div>
    </section>"""


# --------------------------------------------------------------------------- verdict
def verdict_html(a: Analysis, scale: int = 10) -> str:
    c = a.critique
    chips = "".join(
        f'<span class="vchip">{icon("check", 13)} {label}: {fmt_score(getattr(c, key).score, scale)}</span>'
        for label, key in (("Direction", "direction"), ("Visual craft", "cinematography"), ("Story", "screenplay"))
        if valid_score(getattr(c, key).score) is not None
    )
    take = "".join(f"<li>{esc(b)}</li>" for b in c.quick_take)
    words = sum(len(b.split()) for b in c.quick_take)
    ticket = (
        f'<div class="ticket"><div class="sub">Quick take</div><ul>{take}</ul>'
        f'<div class="wc">{words} / {MAX_WORDS} words</div></div>'
        if take
        else ""
    )
    rec = f'<div class="rec">Recommendation: {esc(c.recommendation)}</div>' if c.recommendation.strip() else ""
    return f"""
    <section class="verdict">
      <div class="v-label">{icon("award", 16)} Overall verdict &middot; AI assessment</div>
      <h2>{esc(c.verdict_label or "Overall verdict")}</h2>
      <blockquote>{esc(c.pull_quote)}</blockquote>
      <p class="v-text">{esc(c.verdict_text)}</p>
      <div class="vchips">{chips}</div>
      {rec}
      {ticket}
    </section>"""


# --------------------------------------------------------------------------- recommendations
def reco_card_html(r: Reco, index: int) -> str:
    m = r.movie
    poster = safe_image_url(r.poster_url)
    initial = esc((m.title or "?")[:1].upper())
    inner = (
        f'<img src="{poster}" alt="Poster for {esc(m.title)}" loading="lazy">'
        if poster
        else f'<div class="ph" style="background:{POSTER_GRADIENTS[index % len(POSTER_GRADIENTS)]}">'
        f'<span>{initial}</span></div>'
    )
    meta = " · ".join(x for x in (esc(m.year), esc(m.genre.split(",")[0].strip())) if x)
    return f"""
    <article class="reco">
      <div class="poster">{inner}</div>
      <div class="reco-body">
        <div class="reco-meta">{meta}</div>
        <h3>{esc(m.title)}</h3>
        <p>{esc(m.why)}</p>
      </div>
    </article>"""


def recos_header_html(title: str = "Curated Recommendations Based on Narrative Density & Craft") -> str:
    return f'<div class="eyebrow">Algorithmic affinity cluster</div><h2 class="sec-title">{esc(title)}</h2>'


def fmt_dur(seconds: float | None) -> str:
    if seconds is None:
        return ""
    return f"{seconds * 1000:.0f} ms" if seconds < 1 else f"{seconds:.1f}s"


def timing_html(a: Analysis) -> str:
    run = a.run
    if run is None:
        return ""
    if a.cached:
        text = f"Critique reused from cache &middot; total {fmt_dur(run.elapsed())}"
    else:
        parts = [f"Generated in {fmt_dur(run.elapsed())}"]
        for sid, name in (("analysis", "analysis"), ("recommend", "similar films"), ("tmdb", "TMDB")):
            d = run.duration(sid)
            if d is not None and run.stage(sid).status is Status.COMPLETED:
                parts.append(f"{name} {fmt_dur(d)}")
        text = " &middot; ".join(parts)
    return f'<div class="timing">{text}</div>'


# --------------------------------------------------------------------------- pipeline
_GLYPH = {Status.COMPLETED: "✓", Status.FAILED: "✕", Status.SKIPPED: "–", Status.RUNNING: "●"}


def pipeline_html(run: PipelineRun) -> str:
    """Stage diagram drawn from real execution state (never a hardcoded percentage)."""
    stages, _ = run.view()
    done, total = run.done_count()
    current = run.current_label()
    overall = run.overall
    head_state = {"running": "Running", "completed": "Completed", "partial": "Partially completed",
                  "failed": "Failed"}[overall]
    nodes = []
    for i, st_ in enumerate(stages, 1):
        status = st_.status
        dur = run.duration(st_.id)
        dur_txt = fmt_dur(dur) if dur is not None and status is not Status.PENDING else ""
        glyph = _GLYPH.get(status, str(i))
        par = '<i class="par" title="Runs concurrently with a neighbouring stage">&#8741;</i>' if st_.parallel else ""
        cached = '<span class="cached">cached</span>' if st_.cached else ""
        retries = f'<span class="retry-n">{st_.attempts - 1} retr{"y" if st_.attempts == 2 else "ies"}</span>' if st_.attempts > 1 else ""
        note = esc(st_.note) if st_.note and status is not Status.PENDING else ""
        err = ""
        if st_.error:
            err = f'<span class="err-cat">{esc(CATEGORY_LABELS[st_.error.category])}</span>'
        nodes.append(
            f'<li class="stg s-{status.value}"><span class="dot">{glyph}</span>'
            f'<div class="stg-b"><h4>{esc(st_.label)}{par}</h4>'
            f'<span class="pill-s">{STATUS_LABELS[status]}</span>{cached}{retries}{err}'
            f'<small>{dur_txt}</small><p>{note}</p></div></li>'
        )
    pct = round(100 * done / total)
    legend = " &middot; &#8741; marks stages that run concurrently" if any(x.parallel for x in stages) else ""
    now = f'<span class="pipe-now">Now: {esc(current)}</span>' if current else ""
    return (
        f'<section class="pipe" aria-label="Analysis pipeline">'
        f'<div class="pipe-head"><b>Pipeline</b><span class="pipe-state p-{overall}">{head_state}</span>'
        f'<span>run {esc(run.run_id)}</span><span>Elapsed {fmt_dur(run.elapsed())}</span>{now}</div>'
        f'<div class="pipe-bar" role="progressbar" aria-valuemin="0" aria-valuemax="{total}" aria-valuenow="{done}">'
        f'<span style="width:{pct}%"></span></div>'
        f'<div class="pipe-count">{done} of {total} stages finished{legend}</div>'
        f'<ol class="pipe-flow">{"".join(nodes)}</ol></section>'
    )


def events_html(run: PipelineRun) -> str:
    _, events = run.view()
    if not events:
        return ""
    rows = "".join(
        f'<li class="ev-{e.level}"><span>+{e.t:.2f}s</span><b>{esc(e.stage)}</b><em>{esc(e.level)}</em>{esc(e.message)}</li>'
        for e in events
    )
    return f'<ul class="events" aria-label="Execution events">{rows}</ul>'


def archive_card_html(a: Analysis) -> str:
    c = a.critique
    return (
        f'<div class="arch"><div><h3>{esc(c.title or a.query)}</h3>'
        f'<span>{esc(c.year)} &middot; {esc(c.verdict_label)}</span></div>'
        f"<b>{fmt_score(c.overall_score)}</b></div>"
    )
