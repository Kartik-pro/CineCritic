import { test, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { POST as critique } from "../api/critique";
import { POST as discover } from "../api/discover";
import { POST as ask } from "../api/ask";
import { POST as compare } from "../api/compare";
import { GET as movies } from "../api/movies";
import { extractJson } from "../server/ai";
import { chooseBest, normalizeTitle, parseTitleYear } from "../server/tmdb";
import { critiqueJson, mockFetch, sampleAnalysis } from "./helpers";

const ENV_KEYS = ["TMDB_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "MISTRAL_API_KEY", "AI_PROVIDER", "AI_MODEL"];
let restore: () => void = () => {};
let aiCalls: { url: string; body: any; headers: Record<string, string> }[] = [];
let aiReply: unknown = {};

const movie = (id: number, title: string, year: string, extra = {}) => ({
  id, title, release_date: `${year}-01-01`, overview: "o", poster_path: `/${id}.jpg`, vote_average: 8, vote_count: 100, ...extra,
});

const tmdbData = (url: string): unknown => {
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
  if (u.pathname === "/3/movie/1/recommendations") return { results: [movie(5, "Collateral", "2004")] };
  if (u.pathname === "/3/movie/popular") return { results: [movie(7, "Popular", "2024")], total_pages: 3 };
  return new Response("{}", { status: 404 });
};

beforeEach(() => {
  for (const k of ENV_KEYS) delete process.env[k];
  process.env.TMDB_API_KEY = "abc123";
  process.env.ANTHROPIC_API_KEY = "sk-ant-test";
  aiCalls = [];
  aiReply = critiqueJson();
  restore = mockFetch((url, init) => {
    if (url.includes("themoviedb.org")) return tmdbData(url);
    aiCalls.push({ url, body: JSON.parse(String(init?.body)), headers: init?.headers as Record<string, string> });
    if (url.includes("anthropic.com")) return { content: [{ type: "text", text: typeof aiReply === "string" ? aiReply : JSON.stringify(aiReply) }] };
    if (url.includes("generativelanguage")) return { candidates: [{ content: { parts: [{ text: JSON.stringify(aiReply) }] } }] };
    return { choices: [{ message: { content: typeof aiReply === "string" ? aiReply : JSON.stringify(aiReply) } }] };
  });
});

afterEach(() => restore());

const post = (body: unknown) => new Request("http://x/api", { method: "POST", body: JSON.stringify(body) });

test("title helpers", () => {
  assert.deepEqual(parseTitleYear("Oppenheimer (2023)"), { title: "Oppenheimer", year: "2023" });
  assert.deepEqual(parseTitleYear("Dune: Part Two"), { title: "Dune: Part Two", year: "" });
  assert.equal(normalizeTitle("The Dark Knight!"), "dark knight");
});

test("chooseBest prefers exact title and year, and lists remakes", () => {
  const list = [
    { id: 3, title: "Heat Wave", year: "2000", overview: "", poster: "", rating: null },
    { id: 2, title: "Heat", year: "1986", overview: "", poster: "", rating: null },
    { id: 1, title: "Heat", year: "1995", overview: "", poster: "", rating: null },
  ];
  const picked = chooseBest(list, "Heat", "1995")!;
  assert.equal(picked.best.id, 1);
  assert.deepEqual(picked.alternatives.map((m) => m.id), [2]);
  assert.equal(chooseBest([], "x"), null);
});

test("extractJson handles fences and chatter", () => {
  assert.deepEqual(extractJson('Sure!\n```json\n{"a":1}\n```'), { a: 1 });
  assert.throws(() => extractJson("no json here"));
});

test("critique by query returns analysis, similar films and alternatives", async () => {
  const res = await critique(post({ query: "Heat", spoiler: "none", language: "English" }));
  assert.equal(res.status, 200);
  const data: any = await res.json();
  assert.equal(data.analysis.movie.id, 1);
  assert.equal(data.analysis.movie.director, "Michael Mann");
  assert.equal(data.analysis.movie.runtime, "2h 50m");
  assert.equal(data.analysis.critique.overall, 8);
  assert.equal(data.analysis.similar[0].title, "Collateral");
  assert.equal(data.alternatives.length, 1);
  assert.equal(aiCalls.length, 1);
  assert.match(aiCalls[0]!.body.messages[0].content, /Michael Mann/);
  assert.equal(aiCalls[0]!.headers["x-api-key"], "sk-ant-test");
});

test("critique by id skips search", async () => {
  const res = await critique(post({ id: 1, spoiler: "light", language: "Hindi" }));
  const data: any = await res.json();
  assert.equal(data.analysis.spoiler, "light");
  assert.deepEqual(data.alternatives, []);
  assert.match(aiCalls[0]!.body.system, /write all prose in Hindi/);
});

test("critique applies the spoiler filter and reports it", async () => {
  const raw = critiqueJson() as any;
  raw.verdictText = "Solid. The hero dies at the end.";
  aiReply = raw;
  const data: any = await (await critique(post({ id: 1 }))).json();
  assert.equal(data.analysis.critique.verdictText, "Solid.");
  assert.equal(data.analysis.notices.length, 1);
});

test("critique errors are friendly", async () => {
  assert.equal((await critique(post({ query: "nothing" }))).status, 404);
  assert.equal((await critique(post({ query: "  " }))).status, 400);
  assert.equal((await critique(new Request("http://x", { method: "POST", body: "{{" }))).status, 400);
  delete process.env.ANTHROPIC_API_KEY;
  const res = await critique(post({ id: 1 }));
  assert.equal(res.status, 500);
  assert.match(((await res.json()) as any).error, /No AI provider/);
});

test("provider selection: openai, mistral, gemini", async () => {
  delete process.env.ANTHROPIC_API_KEY;
  process.env.OPENAI_API_KEY = "sk-openai";
  await critique(post({ id: 1 }));
  assert.match(aiCalls[0]!.url, /api\.openai\.com/);
  assert.equal(aiCalls[0]!.body.response_format.type, "json_object");
  assert.equal(aiCalls[0]!.body.messages[0].role, "system");

  process.env.MISTRAL_API_KEY = "m";
  process.env.AI_PROVIDER = "mistral";
  process.env.AI_MODEL = "mistral-small";
  await critique(post({ id: 1 }));
  assert.match(aiCalls[1]!.url, /api\.mistral\.ai/);
  assert.equal(aiCalls[1]!.body.model, "mistral-small");

  process.env.GOOGLE_API_KEY = "g";
  process.env.AI_PROVIDER = "gemini";
  delete process.env.AI_MODEL;
  await critique(post({ id: 1 }));
  assert.match(aiCalls[2]!.url, /gemini-3\.5-flash:generateContent/);
  assert.equal(aiCalls[2]!.body.generationConfig.responseMimeType, "application/json");
  assert.equal(aiCalls[2]!.headers["x-goog-api-key"], "g");
});

test("unreadable AI output is retried once then fails cleanly", async () => {
  aiReply = "not json at all";
  const res = await critique(post({ id: 1 }));
  assert.equal(res.status, 502);
  assert.equal(aiCalls.length, 2);
});

test("provider auth failure never leaks the key", async () => {
  restore();
  restore = mockFetch((url) => (url.includes("themoviedb") ? tmdbData(url) : new Response("bad key sk-ant-test", { status: 401 })));
  const res = await critique(post({ id: 1 }));
  assert.equal(res.status, 500);
  assert.doesNotMatch(await res.text(), /sk-ant-test/);
});

test("discover verifies picks on TMDB and drops unknown ones", async () => {
  aiReply = { picks: [{ title: "Arrival", year: "2016", why: "Cerebral." }, { title: "nothing", year: "1999", why: "x" }, { title: "Arrival", year: "2016", why: "dup" }] };
  const res = await discover(post({ text: "slow sci-fi" }));
  const data: any = await res.json();
  assert.equal(data.picks.length, 1);
  assert.equal(data.picks[0].title, "Arrival");
  assert.equal(data.picks[0].why, "Cerebral.");
  assert.equal((await discover(post({ text: "" }))).status, 400);
});

test("ask passes film context and trims history", async () => {
  aiReply = "Mann uses long lenses.";
  const analysis = sampleAnalysis();
  const history = [
    { role: "assistant", content: "stale" },
    { role: "user", content: "hi" },
    { role: "assistant", content: "hello" },
  ];
  const data: any = await (await ask(post({ question: "How is it shot?", history, analysis, spoiler: "none" }))).json();
  assert.equal(data.answer, "Mann uses long lenses.");
  const body = aiCalls[0]!.body;
  assert.match(body.system, /FILM: Heat \(1995\)/);
  assert.equal(body.messages[0].role, "user");
  assert.equal(body.messages.at(-1).content, "How is it shot?");
  assert.equal(body.messages.length, 3);
});

test("ask removes spoilers unless full spoilers are on", async () => {
  aiReply = "Great pacing. Everyone dies in the end.";
  const safe: any = await (await ask(post({ question: "q", spoiler: "none" }))).json();
  assert.equal(safe.answer, "Great pacing.");
  const full: any = await (await ask(post({ question: "q", spoiler: "full" }))).json();
  assert.match(full.answer, /dies/);
  assert.equal((await ask(post({ question: " " }))).status, 400);
});

test("compare writes a narrative from both analyses", async () => {
  aiReply = "Both are strong. Overall: depends on mood.";
  const res = await compare(post({ a: sampleAnalysis("Heat"), b: sampleAnalysis("Collateral", { plot: 5 }), spoiler: "none" }));
  const data: any = await res.json();
  assert.match(data.narrative, /Overall/);
  assert.match(aiCalls[0]!.body.messages[0].content, /FILM A: Heat[\s\S]*FILM B: Collateral/);
  assert.equal((await compare(post({ a: sampleAnalysis(), b: {} }))).status, 400);
});

test("movies: search, lists and validation", async () => {
  const search: any = await (await movies(new Request("http://x/api/movies?q=Heat"))).json();
  assert.equal(search.items.length, 3);
  assert.deepEqual(((await (await movies(new Request("http://x/api/movies?q=a"))).json()) as any).items, []);
  const list: any = await (await movies(new Request("http://x/api/movies?list=popular&page=2"))).json();
  assert.equal(list.items[0].title, "Popular");
  assert.equal(list.totalPages, 3);
  assert.equal((await movies(new Request("http://x/api/movies?list=bogus"))).status, 400);
  delete process.env.TMDB_API_KEY;
  assert.equal((await movies(new Request("http://x/api/movies?q=Heat"))).status, 500);
});
