"""Pydantic schemas for structured LLM output, plus score helpers."""
from __future__ import annotations

from pydantic import BaseModel, Field

NO_SCORE = -1.0


class Movie(BaseModel):
    title: str = Field(description="Exact movie title")
    year: str = Field(description="Release year")
    genre: str = Field(description="Genres, comma separated")
    why: str = Field(description="Why it fits the user's taste, under 15 words")


class Recommendations(BaseModel):
    recommendations: list[Movie]


class Dimension(BaseModel):
    score: float = Field(
        description=(
            "Your own critical assessment from 0 to 10 with one decimal. Be honest and "
            "discriminating; weak aspects deserve low scores. Use -1 if you cannot assess it."
        )
    )
    summary: str = Field(description="Headline judgement, at most 35 words")
    detail: str = Field(description="Supporting analysis explaining the technique, at most 40 words")
    reference: str = Field(
        description="Short 1-3 word UPPERCASE label naming the craft element, or empty string"
    )


class Critique(BaseModel):
    recognized: bool = Field(
        description="False if you do not confidently recognise this as a real, released film"
    )
    title: str = Field(description="Canonical film title")
    year: str = Field(description="Release year, or empty string if unsure")
    genre: str = Field(description="Genres, comma separated, or empty string if unsure")
    runtime: str = Field(description="Runtime like '3h 0m', or empty string if unsure")
    director: str = Field(description="Director, or empty string if not certain")
    cinematographer: str = Field(description="Cinematographer, or empty string if not certain")
    composer: str = Field(description="Composer, or empty string if not certain")

    plot: Dimension
    screenplay: Dimension
    direction: Dimension
    acting: Dimension
    cinematography: Dimension
    music: Dimension
    pacing: Dimension
    themes: Dimension

    strengths: list[str] = Field(description="2-3 major strengths, each at most 20 words")
    flaws: list[str] = Field(description="1-3 genuine weaknesses, each at most 20 words")

    overall_score: float = Field(description="Overall CineCritic score 0-10, or -1 if unassessable")
    verdict_label: str = Field(
        description="Short editorial verdict title, e.g. 'A Divisive but Ambitious Film'"
    )
    pull_quote: str = Field(
        description="One memorable sentence summarising the film, at most 25 words"
    )
    verdict_text: str = Field(description="Supporting verdict paragraph, at most 45 words")
    recommendation: str = Field(description="Viewing recommendation, at most 12 words")
    quick_take: list[str] = Field(
        description="4-5 short bullets; the ENTIRE list must total at most 50 words"
    )
    themes_tags: list[str] = Field(
        default_factory=list,
        description="2-4 thematic tags of 1-3 words each (your interpretation, e.g. 'obsession', 'found family')",
    )
    spoiler_notes: str = Field(
        default="",
        description="Spoiler-containing analysis, at most 80 words. Leave EMPTY unless the instructions allow spoilers",
    )


class SearchFilters(BaseModel):
    genres: list[str] = Field(default_factory=list, description="Genre names from the allowed list")
    year_from: int = Field(default=0, description="Earliest release year or 0")
    year_to: int = Field(default=0, description="Latest release year or 0")
    language: str = Field(default="", description="ISO 639-1 original-language code or empty")


def valid_score(value: float | None) -> float | None:
    """Return the score if it is a genuine 0-10 value, else None (never invent one)."""
    if value is None:
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score if 0.0 <= score <= 10.0 else None
