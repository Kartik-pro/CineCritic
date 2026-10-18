import { DIMENSIONS, type Critique, type DimensionKey } from "./types";

export type Scores = Record<DimensionKey, number | null>;

const TIE_MARGIN = 0.3;
const WINNER_MARGIN = 0.5;
const MIN_COMPARABLE = 4;

const BANDS: [number, string][] = [
  [9, "Exceptional"],
  [8, "Excellent"],
  [7, "Strong"],
  [6, "Solid"],
  [5, "Mixed"],
  [3, "Weak"],
  [0, "Poor"],
];

export function validScore(value: unknown): number | null {
  const n = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  return Number.isFinite(n) && n >= 0 && n <= 10 ? Math.round(n * 10) / 10 : null;
}

export function dimensionScores(critique: Critique): Scores {
  const out = {} as Scores;
  for (const { key } of DIMENSIONS) out[key] = validScore(critique.dimensions[key]?.score);
  return out;
}

export function average(scores: Partial<Record<DimensionKey, number | null>>): number | null {
  const values = Object.values(scores).filter((v): v is number => typeof v === "number");
  if (!values.length) return null;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

export function overallScore(critique: Critique): number | null {
  return validScore(critique.overall) ?? average(dimensionScores(critique));
}

export function band(score: number | null): string {
  if (score === null) return "Not assessed";
  return BANDS.find(([floor]) => score >= floor)?.[1] ?? "Poor";
}

export type Outcome = "a" | "b" | "tie" | "unknown";
export type Leader = "a" | "b" | "close" | "inconclusive";

export interface Comparison {
  rows: { key: DimensionKey; a: number | null; b: number | null; outcome: Outcome }[];
  overallA: number | null;
  overallB: number | null;
  leader: Leader;
  comparable: number;
}

export function compareScores(a: Scores, b: Scores): Comparison {
  const rows = DIMENSIONS.map(({ key }) => {
    const x = a[key];
    const y = b[key];
    let outcome: Outcome = "unknown";
    if (x !== null && y !== null) outcome = Math.abs(x - y) < TIE_MARGIN ? "tie" : x > y ? "a" : "b";
    return { key, a: x, b: y, outcome };
  });
  const shared = rows.filter((r) => r.outcome !== "unknown");
  const overallA = average(Object.fromEntries(shared.map((r) => [r.key, r.a])));
  const overallB = average(Object.fromEntries(shared.map((r) => [r.key, r.b])));
  let leader: Leader = "inconclusive";
  if (overallA !== null && overallB !== null && shared.length >= MIN_COMPARABLE) {
    if (Math.abs(overallA - overallB) < WINNER_MARGIN) leader = "close";
    else leader = overallA > overallB ? "a" : "b";
  }
  return { rows, overallA, overallB, leader, comparable: shared.length };
}
