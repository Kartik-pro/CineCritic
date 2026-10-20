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

export const movie = (id: number, title: string, year: string, extra = {}) => ({
  id, title, release_date: `${year}-01-01`, overview: "o", poster_path: `/${id}.jpg`, vote_average: 8, vote_count: 100, ...extra,
});

export const tmdbData = (url: string): unknown => {
  const u = new URL(url);
  if (u.pathname === "/3/search/movie") {
    const q = u.searchParams.get("query");
    if (q === "nothing") return { results: [] };
    if (q === "Heat") return { results: [movie(1, "Heat", "1995"), movie(2, "Heat", "1986"), movie(3, "Heat Wave", "2000")] };
    return { results: [movie(10, String(q), "2020")] };
  }
  if (u.pathname === "/3/movie/1") {
    return {
      ...movie(1, "Heat", "1995"), runtime: 170, genres: [{ name: "Crime" }], tagline: "t", backdrop_path: "/b.jpg",
      credits: { crew: [{ job: "Director", name: "Michael Mann" }], cast: [{ name: "Al Pacino", character: "Vincent" }] },
    };
  }
  if (u.pathname === "/3/movie/10") return { ...movie(10, "Arrival", "2016"), runtime: 116, genres: [{ name: "Sci-Fi" }], credits: { crew: [], cast: [] } };
  if (u.pathname === "/3/movie/1/recommendations") return { results: [movie(5, "Collateral", "2004")] };
  if (u.pathname === "/3/movie/popular") return { results: [movie(7, "Popular", "2024")], total_pages: 3 };
  return new Response("{}", { status: 404 });
};


export interface StreamOutcome {
  events: any[];
  result?: any;
  error?: any;
  status: number;
}

export async function readStream(res: Response): Promise<StreamOutcome> {
  const text = await res.text();
  const outcome: StreamOutcome = { events: [], status: res.status };
  for (const line of text.split("\n").filter(Boolean)) {
    const message = JSON.parse(line);
    if (message.type === "event") outcome.events.push(message.event);
    else if (message.type === "result") outcome.result = message.data;
    else if (message.type === "error") outcome.error = message.error;
  }
  return outcome;
}
