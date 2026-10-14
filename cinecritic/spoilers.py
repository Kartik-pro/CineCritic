"""Spoiler protection.

Protection is applied to the generated text itself, not only to what the UI shows:

* Every main section of an analysis (summaries, scorecards, strengths, verdict, quick take) is
  ALWAYS requested and enforced as spoiler-free.
* The only place plot specifics may appear is `Critique.spoiler_notes`, and the model is asked
  to fill it only when the user's tolerance allows (light = set-up beyond the premise but no
  outcomes; full = anything, including the ending).
* A heuristic sentence filter removes spoiler cues that slip through and reports how many
  sentences it removed. It is a safety net, not a guarantee: AI output can never be proven
  spoiler-free, which the UI states.
* Spoiler notes are only rendered after an explicit reveal click, and never in previews,
  archives lists, exports (unless the user opts in) or collapsed containers.
"""
from __future__ import annotations

import re

from .schemas import Critique

LEVELS = ("none", "light", "full")
LABELS = {
    "none": "Spoiler-free",
    "light": "Light spoilers (no endings or outcomes)",
    "full": "Full spoilers (including the ending)",
}
PLACEHOLDER = "Details withheld to avoid spoilers."

# Outcome cues are removed everywhere except in full-spoiler notes.
_OUTCOME = re.compile(
    r"\b(dies|die|died|killed|kills|murders?|murdered|the killer|death of|survives|survived|"
    r"turns out|is revealed|are revealed|revealed to be|reveals that|the twist|plot twist|final twist|"
    r"twist ending|the ending|the finale|in the end|by the end|ultimately|betrays|betrayed|"
    r"is actually|was actually|the real (?:villain|killer|culprit)|sacrifices?)\b", re.I)
# Extra cues removed from spoiler-free text only (suggestive of plot developments).
_EXTRA = re.compile(r"\b(reveals?|revealed|revelations?|reversal|shocking|unexpected turn|climax|third act|final act|ending|"
                    r"last act|eventually|later (?:learns?|discovers?)|discovers? that|learns? that)\b", re.I)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def instructions(level: str) -> str:
    """Prompt block appended to the system prompt."""
    base = (
        "\n\nSPOILER POLICY (mandatory): every field EXCEPT spoiler_notes must be completely "
        "spoiler-free. Describe only the premise and set-up, tone, craft and technique. Never reveal "
        "plot twists, who lives or dies, how anything resolves, the ending, or major reveals, and do "
        "not hint at them (no 'the ending', 'the twist', 'in the end'). "
    )
    if level == "full":
        return base + ("spoiler_notes: write at most 80 words of spoiler-containing analysis (key developments, "
                       "the ending and what it means). It is hidden from the user until they choose to reveal it.")
    if level == "light":
        return base + ("spoiler_notes: write at most 80 words covering plot developments up to the midpoint only. "
                       "Do NOT reveal the ending, deaths, twists or outcomes.")
    return base + "spoiler_notes: leave it as an empty string."


def scan(text: str, level: str = "none") -> list[str]:
    """Return the spoiler cues found in `text` (empty list = clean)."""
    hits = [m.group(0).lower() for m in _OUTCOME.finditer(text or "")]
    if level == "none":
        hits += [m.group(0).lower() for m in _EXTRA.finditer(text or "")]
    return hits


def clean_text(text: str, level: str = "none") -> tuple[str, int]:
    """Drop sentences that contain spoiler cues. Returns (clean_text, sentences_removed)."""
    if not text or not scan(text, level):
        return text, 0
    kept, removed = [], 0
    for sentence in _SENTENCE.split(text.strip()):
        if scan(sentence, level):
            removed += 1
        else:
            kept.append(sentence)
    return (" ".join(kept) if kept else PLACEHOLDER), removed


def enforce(critique: Critique, level: str = "none") -> int:
    """Sanitise `critique` in place; returns how many sentences were removed in total."""
    removed = 0

    def fix(value: str) -> str:
        nonlocal removed
        out, n = clean_text(value, "none")
        removed += n
        return out

    for field in ("plot", "screenplay", "direction", "acting", "cinematography", "music", "pacing", "themes"):
        dim = getattr(critique, field)
        dim.summary, dim.detail = fix(dim.summary), fix(dim.detail)
    critique.strengths = [fix(s) for s in critique.strengths]
    critique.flaws = [fix(s) for s in critique.flaws]
    critique.pull_quote = fix(critique.pull_quote)
    critique.verdict_text = fix(critique.verdict_text)
    critique.quick_take = [fix(s) for s in critique.quick_take]
    critique.themes_tags = [t for t in critique.themes_tags if not scan(t, "none")][:4]
    if level == "none":
        critique.spoiler_notes = ""
    elif level == "light":
        critique.spoiler_notes, n = clean_text(critique.spoiler_notes, "light")
        removed += n
    critique.spoiler_notes = (critique.spoiler_notes or "")[:700]
    return removed


def effective_level(requested: str) -> str:
    return requested if requested in LEVELS else "none"
