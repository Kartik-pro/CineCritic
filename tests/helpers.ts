import type { Critique, Analysis, DimensionKey } from "../shared/types";
import { DIMENSIONS } from "../shared/types";

type Handler = (url: string, init?: RequestInit) => unknown | Promise<unknown>;

export function mockFetch(handler: Handler): () => void {
  const original = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    const result = await handler(url, init);
    if (result instanceof Response) return result;
    return new Response(JSON.stringify(result), { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  return () => {
    globalThis.fetch = original;
  };
}

export function critiqueJson(score = 8): Record<string, unknown> {
  const raw: Record<string, unknown> = {};
  for (const { key } of DIMENSIONS) raw[key] = { score, summary: `${key} summary.`, detail: `${key} detail.` };
  return {
    ...raw,
    overall: score,
    verdictLabel: "A Strong Film",
    verdictText: "Confident and well made.",
    pullQuote: "A quiet triumph.",
    recommendation: "Watch on the biggest screen.",
    quickTake: ["Gripping tone.", "Great acting.", "Sharp direction.", "Score 8/10."],
    strengths: ["Direction"],
    flaws: ["Runtime"],
    tags: ["obsession"],
    spoilerNotes: "",
  };
}

export function sampleAnalysis(title = "Heat", scores: Partial<Record<DimensionKey, number>> = {}): Analysis {
  const dimensions = {} as Critique["dimensions"];
  for (const { key } of DIMENSIONS) dimensions[key] = { score: scores[key] ?? 8, summary: "s", detail: "d" };
  return {
    movie: {
      id: 1, title, year: "1995", overview: "o", poster: "", rating: 8, runtime: "2h 50m", genres: ["Crime"],
      director: "Michael Mann", cinematographer: "", composer: "", cast: [{ name: "Al Pacino", character: "Vincent" }],
      tagline: "", backdrop: "",
    },
    critique: {
      dimensions, overall: 8, verdictLabel: "Great", verdictText: "Great film.", pullQuote: "q", recommendation: "r",
      quickTake: ["a"], strengths: ["x"], flaws: ["y"], tags: [], spoilerNotes: "",
    },
    similar: [], spoiler: "none", language: "English", notices: [], createdAt: 0,
  };
}
