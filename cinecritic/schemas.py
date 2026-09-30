"""Pydantic schemas for structured LLM output."""
from __future__ import annotations

from pydantic import BaseModel, Field


class Movie(BaseModel):
    title: str = Field(description="Exact movie title")
    year: str = Field(description="Release year")
    genre: str = Field(description="Genres, comma separated")
    why: str = Field(description="Why it fits the user's taste, under 15 words")


class Recommendations(BaseModel):
    recommendations: list[Movie]
