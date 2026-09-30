"""Prompt templates for reviews and recommendations."""
from __future__ import annotations

from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate

from .config import MAX_WORDS
from .prompt_template import Cine_prompt

BULLET_RULES = (
    "\n\nOUTPUT RULES (override everything above): reply ONLY with 4-5 short bullet points, "
    f"each starting with '- '. The ENTIRE reply must be at most {MAX_WORDS} words in total. "
    "Cover plot vibe, acting, direction, strengths/weakness, and a final verdict with a score "
    "out of 10. No headings, no intro, no outro."
)

# SystemMessage (not a plain tuple) so braces inside Cine_prompt are never parsed as variables.
REVIEW_TEMPLATE = ChatPromptTemplate.from_messages(
    [
        SystemMessage(content=Cine_prompt + BULLET_RULES),
        ("human", "Review the movie: {movie_name}"),
    ]
)

RECOMMEND_TEMPLATE = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are CineCritic, a film expert. Given the user's input (a movie they love, a "
            "mood, or a genre), recommend exactly {n} real movies. Never recommend the movie "
            "they mentioned. Mix popular picks with hidden gems. Keep each 'why' under 15 words.",
        ),
        ("human", "User input: {user_input}"),
    ]
)
