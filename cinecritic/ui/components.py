"""Pure HTML builders for the hero, review ticket and movie cards."""
from __future__ import annotations

import html

from ..schemas import Movie

GRADIENTS = [
    "linear-gradient(135deg,#e50914,#4a0509)",
    "linear-gradient(135deg,#5a2ca0,#1b0f3a)",
    "linear-gradient(135deg,#0f8b8d,#062f3a)",
    "linear-gradient(135deg,#f5a623,#5c2e00)",
    "linear-gradient(135deg,#2b6cb0,#0b1b3a)",
    "linear-gradient(135deg,#c2185b,#3a0620)",
]


def hero_html() -> str:
    return (
        '<div class="hero"><div class="strip"></div>'
        '<div class="title">CINECRITIC</div>'
        '<div class="tag">Quick Reviews · Smart Picks · Your Pocket Critic</div></div>'
    )


def ticket_html(title: str, bullets: list[str], max_words: int) -> str:
    items = "".join(f"<li>{html.escape(b)}</li>" for b in bullets)
    words = sum(len(b.split()) for b in bullets)
    return f"""
    <div class="ticket">
      <div class="sub">Now Reviewing</div>
      <h2>{html.escape(title.strip().title())}</h2><hr>
      <ul>{items}</ul>
      <div class="wc">{words} / {max_words} WORDS</div>
    </div>"""


def movie_card_html(movie: Movie, index: int) -> str:
    pills = "".join(
        f'<span class="pill">{html.escape(g.strip())}</span>' for g in movie.genre.split(",")
    )
    return f"""
    <div class="mcard">
      <div class="poster" style="background:{GRADIENTS[index % len(GRADIENTS)]}">
        {html.escape(movie.title[:1].upper())}</div>
      <div class="mbody"><h3>{html.escape(movie.title)}</h3>
        <div class="year">{html.escape(movie.year)}</div>{pills}
        <div class="why">{html.escape(movie.why)}</div></div>
    </div>"""
