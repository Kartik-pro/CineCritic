import { test, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { GET as movies } from "../api/movies";
import { GET as status } from "../api/status";
import { extractJson } from "../server/ai";
import { chooseBest, normalizeTitle, parseTitleYear } from "../server/tmdb";
import { mockFetch, tmdbData } from "./helpers";

const ENV_KEYS = ["TMDB_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "MISTRAL_API_KEY", "HF_TOKEN", "AI_PROVIDER", "AI_MODEL"];
let restore: () => void = () => {};

beforeEach(() => {
  for (const k of ENV_KEYS) delete process.env[k];
  process.env.TMDB_API_KEY = "abc123";
  process.env.ANTHROPIC_API_KEY = "sk-ant-test";
  restore = mockFetch((url) => (url.includes("themoviedb.org") ? tmdbData(url) : {}));
});

afterEach(() => restore());

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

test("status reports which keys are available", async () => {
  const ask = (headers: Record<string, string> = {}) => status(new Request("http://x/api/status", { headers }));
  assert.deepEqual(await (await ask()).json(), { tmdb: true, ai: true });
  delete process.env.TMDB_API_KEY;
  delete process.env.ANTHROPIC_API_KEY;
  assert.deepEqual(await (await ask()).json(), { tmdb: false, ai: false });
  assert.deepEqual(await (await ask({ "x-tmdb-key": "a", "x-ai-key": "b" })).json(), { tmdb: true, ai: true });
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
  assert.equal((await movies(new Request("http://x/api/movies?q=Heat"))).status, 401);
});
