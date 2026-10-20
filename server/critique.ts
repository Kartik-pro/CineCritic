import { DIMENSIONS, type Critique, type Dimension, type DimensionKey, type MovieDetails, type SpoilerLevel } from "../shared/types.js";
import { validScore } from "../shared/scoring.js";
import { generateJson, type InferOptions } from "./ai.js";
import { AppError } from "./errors.js";
import { QUICK_TAKE_WORDS, critiqueSystem } from "./prompts.js";
import { enforce } from "./spoilers.js";
import { facts } from "./tmdb.js";

const text = (value: unknown, max = 400): string => (typeof value === "string" ? value.trim().slice(0, max) : "");

const list = (value: unknown, max: number, each = 200): string[] =>
  (Array.isArray(value) ? value : [])
    .map((item) => text(item, each))
    .filter(Boolean)
    .slice(0, max);

export function capWords(lines: string[], limit = QUICK_TAKE_WORDS): string[] {
  const out: string[] = [];
  let used = 0;
  for (const line of lines) {
    const words = line.replace(/^[-•*\d.)\s]+/, "").replace(/\*\*/g, "").split(/\s+/).filter(Boolean);
    if (used + words.length > limit) {
      const left = limit - used;
      if (left >= 3) out.push(words.slice(0, left).join(" ").replace(/[,;:]$/, "") + "…");
      break;
    }
    if (words.length) out.push(words.join(" "));
    used += words.length;
  }
  return out;
}

export function sanitizeCritique(raw: Record<string, unknown>): Critique {
  const dimensions = {} as Record<DimensionKey, Dimension>;
  for (const { key } of DIMENSIONS) {
    const item = (raw[key] ?? {}) as Record<string, unknown>;
    dimensions[key] = { score: validScore(item.score), summary: text(item.summary, 300), detail: text(item.detail, 360) };
  }
  return {
    dimensions,
    overall: validScore(raw.overall),
    verdictLabel: text(raw.verdictLabel, 120),
    verdictText: text(raw.verdictText, 400),
    pullQuote: text(raw.pullQuote, 240),
    recommendation: text(raw.recommendation, 120),
    quickTake: capWords(list(raw.quickTake, 6, 300)),
    strengths: list(raw.strengths, 3),
    flaws: list(raw.flaws, 3),
    tags: list(raw.tags, 4, 40),
    spoilerNotes: text(raw.spoilerNotes, 900),
  };
}

export const hasContent = (critique: Critique): boolean =>
  critique.overall !== null || DIMENSIONS.some(({ key }) => critique.dimensions[key].score !== null);

export function generateCritique(movie: MovieDetails, spoiler: SpoilerLevel, language: string, options: Omit<InferOptions, "system" | "messages">) {
  return generateJson({
    ...options,
    system: critiqueSystem(spoiler, language),
    messages: [
      {
        role: "user",
        content: `Analyse the film: ${movie.title}${movie.year ? ` (${movie.year})` : ""}\n\nVerified facts (TMDB):\n${facts(movie)}`,
      },
    ],
  });
}

export function parseCritique(raw: Record<string, unknown>): Critique {
  const critique = sanitizeCritique(raw);
  if (!hasContent(critique)) throw new AppError("malformed_output", { message: "The AI response did not contain a usable analysis." });
  return critique;
}
