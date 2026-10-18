import type { Critique, SpoilerLevel } from "../shared/types";
import { DIMENSIONS, SPOILER_LEVELS } from "../shared/types";

const PLACEHOLDER = "Details withheld to avoid spoilers.";

const OUTCOME =
  /\b(dies|die|died|killed|kills|murders?|murdered|the killer|death of|survives|survived|turns out|is revealed|are revealed|revealed to be|reveals that|the twist|plot twist|final twist|twist ending|the ending|the finale|in the end|by the end|ultimately|betrays|betrayed|is actually|was actually|the real (?:villain|killer|culprit)|sacrifices?)\b/i;

const EXTRA =
  /\b(reveals?|revealed|revelations?|reversal|shocking|unexpected turn|climax|third act|final act|ending|last act|eventually|later (?:learns?|discovers?)|discovers? that|learns? that)\b/i;

export function effectiveLevel(value: unknown): SpoilerLevel {
  return SPOILER_LEVELS.includes(value as SpoilerLevel) ? (value as SpoilerLevel) : "none";
}

export function spoilerInstructions(level: SpoilerLevel): string {
  const base =
    "SPOILER POLICY (mandatory): every field EXCEPT spoilerNotes must be completely spoiler-free. Describe only the premise and set-up, tone, craft and technique. Never reveal plot twists, who lives or dies, how anything resolves, the ending, or major reveals, and do not hint at them. ";
  if (level === "full")
    return base + "spoilerNotes: at most 80 words of spoiler-containing analysis (key developments, the ending and what it means). It stays hidden until the user chooses to reveal it.";
  if (level === "light")
    return base + "spoilerNotes: at most 80 words covering plot developments up to the midpoint only. Do NOT reveal the ending, deaths, twists or outcomes.";
  return base + 'spoilerNotes: must be an empty string.';
}

function hasSpoiler(text: string, strict: boolean): boolean {
  return OUTCOME.test(text) || (strict && EXTRA.test(text));
}

export function stripSpoilers(text: string, strict: boolean): { text: string; removed: number } {
  if (!text || !hasSpoiler(text, strict)) return { text, removed: 0 };
  const sentences = text.trim().split(/(?<=[.!?])\s+/);
  const kept = sentences.filter((s) => !hasSpoiler(s, strict));
  return { text: kept.length ? kept.join(" ") : PLACEHOLDER, removed: sentences.length - kept.length };
}

export function enforce(critique: Critique, level: SpoilerLevel): number {
  let removed = 0;
  const fix = (value: string) => {
    const result = stripSpoilers(value, true);
    removed += result.removed;
    return result.text;
  };
  for (const { key } of DIMENSIONS) {
    const dimension = critique.dimensions[key];
    dimension.summary = fix(dimension.summary);
    dimension.detail = fix(dimension.detail);
  }
  critique.strengths = critique.strengths.map(fix);
  critique.flaws = critique.flaws.map(fix);
  critique.quickTake = critique.quickTake.map(fix);
  critique.pullQuote = fix(critique.pullQuote);
  critique.verdictText = fix(critique.verdictText);
  critique.tags = critique.tags.filter((tag) => !hasSpoiler(tag, true)).slice(0, 4);

  if (level === "none") critique.spoilerNotes = "";
  else if (level === "light") {
    const result = stripSpoilers(critique.spoilerNotes, false);
    critique.spoilerNotes = result.text;
    removed += result.removed;
  }
  critique.spoilerNotes = critique.spoilerNotes.slice(0, 700);
  return removed;
}
