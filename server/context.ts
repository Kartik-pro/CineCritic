import { DIMENSIONS, type Analysis, type SpoilerLevel } from "../shared/types";
import { dimensionScores, type Comparison } from "../shared/scoring";
import { facts } from "./tmdb";

export function isAnalysis(value: unknown): value is Analysis {
  const a = value as Analysis | null;
  return (
    !!a &&
    typeof a === "object" &&
    typeof a.movie?.title === "string" &&
    Array.isArray(a.movie.genres) &&
    Array.isArray(a.movie.cast) &&
    !!a.critique?.dimensions &&
    DIMENSIONS.every(({ key }) => typeof a.critique.dimensions[key] === "object" && a.critique.dimensions[key] !== null) &&
    Array.isArray(a.critique.strengths) &&
    Array.isArray(a.critique.flaws)
  );
}

function scoreLines(a: Analysis): string {
  const scores = dimensionScores(a.critique);
  return DIMENSIONS.filter(({ key }) => scores[key] !== null)
    .map(({ key, title }) => `- ${title}: ${scores[key]!.toFixed(1)}/10 — ${a.critique.dimensions[key].summary}`)
    .join("\n");
}

export function filmContext(a: Analysis, spoiler: SpoilerLevel): string {
  const c = a.critique;
  const lines = [
    `FILM: ${a.movie.title}${a.movie.year ? ` (${a.movie.year})` : ""}`,
    `${facts(a.movie)}  [verified by TMDB]`,
    "CINECRITIC ANALYSIS (AI opinion, not fact):",
    scoreLines(a),
  ];
  if (c.verdictLabel) lines.push(`- Verdict: ${c.verdictLabel}. ${c.verdictText}`);
  if (c.strengths.length) lines.push(`- Strengths: ${c.strengths.join("; ")}`);
  if (c.flaws.length) lines.push(`- Weaknesses: ${c.flaws.join("; ")}`);
  if (spoiler !== "none" && c.spoilerNotes) lines.push(`- Spoiler notes (${spoiler}): ${c.spoilerNotes}`);
  return lines.join("\n").slice(0, 6000);
}

export function comparisonContext(a: Analysis, b: Analysis, comparison: Comparison): string {
  const block = (tag: string, x: Analysis) =>
    `FILM ${tag}: ${x.movie.title}${x.movie.year ? ` (${x.movie.year})` : ""}\n${facts(x.movie)}\nVerdict: ${x.critique.verdictLabel}. ${x.critique.verdictText}\nStrengths: ${x.critique.strengths.join("; ")}\nWeaknesses: ${x.critique.flaws.join("; ")}\n${scoreLines(x)}`;
  const outcomes = comparison.rows
    .map((r) => `${DIMENSIONS.find((d) => d.key === r.key)!.short}: ${r.outcome}`)
    .join(", ");
  return `${block("A", a)}\n\n${block("B", b)}\n\nSCORE COMPARISON (A vs B): ${outcomes}\nLeader by rule: ${comparison.leader}`.slice(0, 12000);
}
