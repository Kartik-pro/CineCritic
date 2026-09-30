"""Business logic: generate reviews and recommendations (UI-independent)."""
from __future__ import annotations

import re

from .config import MAX_WORDS
from .prompts import RECOMMEND_TEMPLATE, REVIEW_TEMPLATE
from .schemas import Movie, Recommendations


def to_text(content) -> str:
    """Normalize a model response: Mistral returns str, Gemini a list of blocks."""
    if isinstance(content, str):
        return content
    return "\n".join(
        block["text"] if isinstance(block, dict) else str(block)
        for block in content
        if not isinstance(block, dict) or "text" in block
    )


def to_bullets(text: str, max_words: int = MAX_WORDS) -> list[str]:
    """Split text into bullets and hard-cap the total word count."""
    lines = [
        re.sub(r"^\s*[-•*\d.)]+\s*", "", line).replace("**", "").strip()
        for line in text.splitlines()
        if line.strip()
    ]
    bullets: list[str] = []
    used = 0
    for line in lines:
        words = line.split()
        if used + len(words) > max_words:
            left = max_words - used
            if left >= 3:
                bullets.append(" ".join(words[:left]).rstrip(",;:") + "…")
            break
        bullets.append(line)
        used += len(words)
    return bullets


def review_movie(llm, movie_name: str) -> list[str]:
    prompt = REVIEW_TEMPLATE.invoke({"movie_name": movie_name})
    return to_bullets(to_text(llm.invoke(prompt).content))


def recommend_movies(llm, user_input: str, n: int) -> list[Movie]:
    chain = RECOMMEND_TEMPLATE | llm.with_structured_output(Recommendations)
    return chain.invoke({"user_input": user_input, "n": n}).recommendations
