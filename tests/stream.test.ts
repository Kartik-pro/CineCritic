import { test, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { POST as critique } from "../api/critique";
import { POST as discover } from "../api/discover";
import { POST as ask } from "../api/ask";
import { POST as battle } from "../api/battle";
import { POST as connection } from "../api/connection";
import { GET as models } from "../api/models";
import { critiqueJson, mockFetch, readStream, sampleAnalysis, tmdbData } from "./helpers";

const ENV_KEYS = ["TMDB_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "MISTRAL_API_KEY", "HF_TOKEN", "AI_PROVIDER", "AI_MODEL"];
let restore: () => void = () => {};
let aiCalls: { url: string; body: any; headers: Record<string, string> }[] = [];
let aiReply: unknown = {};
let aiStatus: number[] = [];

const text = () => (typeof aiReply === "string" ? aiReply : JSON.stringify(aiReply));

beforeEach(() => {
  for (const k of ENV_KEYS) delete process.env[k];
  process.env.TMDB_API_KEY = "abc123";
  process.env.ANTHROPIC_API_KEY = "sk-ant-test";
  aiCalls = [];
  aiStatus = [];
  aiReply = critiqueJson();
  restore = mockFetch((url, init) => {
    if (url.includes("themoviedb.org")) return tmdbData(url);
    if (init?.method === "GET" || !init?.body) return {};
    aiCalls.push({ url, body: JSON.parse(String(init.body)), headers: init.headers as Record<string, string> });
    const forced = aiStatus.shift();
    if (forced) return new Response("bad key sk-ant-test", { status: forced });
    if (url.includes("anthropic.com")) return { content: [{ type: "text", text: text() }], usage: { input_tokens: 11, output_tokens: 7 } };
    if (url.includes("generativelanguage")) return { candidates: [{ content: { parts: [{ text: text() }] } }] };
    return { choices: [{ message: { content: text() } }] };
  });
});

afterEach(() => restore());

const post = (body: unknown, headers: Record<string, string> = {}) =>
  new Request("http://x/api", { method: "POST", body: JSON.stringify(body), headers });

test("critique streams ordered events then a result", async () => {
  const out = await readStream(await critique(post({ query: "Heat", executionId: "run-12345678" })));
  assert.equal(out.error, undefined);
  assert.equal(out.result.analysis.movie.id, 1);
  assert.equal(out.result.analysis.critique.overall, 8);
  assert.equal(out.result.analysis.similar[0].title, "Collateral");
  assert.equal(out.result.alternatives.length, 1);
  assert.deepEqual(out.result.analysis.generatedBy, { provider: "anthropic", model: "claude-sonnet-5-5" });
  assert.ok(out.events.every((e) => e.executionId === "run-12345678"));
  const seqs = out.events.map((e) => e.seq);
  assert.deepEqual(seqs, [...seqs].sort((a, b) => a - b));
  assert.equal(new Set(seqs).size, seqs.length);
  const completed = out.events.filter((e) => e.status === "completed").map((e) => e.stageId);
  assert.deepEqual(completed, ["validate", "prepare", "lookup", "details", "inference", "validate_output", "spoiler", "finalize"]);
  const inference = out.events.find((e) => e.stageId === "inference" && e.status === "completed");
  assert.match(inference.message, /11 in \/ 7 out tokens/);
  assert.equal(aiCalls.length, 1);
  assert.match(aiCalls[0]!.body.messages[0].content, /Michael Mann/);
  assert.equal(aiCalls[0]!.headers["x-api-key"], "sk-ant-test");
});

test("critique by id skips the lookup stage", async () => {
  const out = await readStream(await critique(post({ id: 1, spoiler: "light", language: "Hindi" })));
  assert.equal(out.result.analysis.spoiler, "light");
  assert.deepEqual(out.result.alternatives, []);
  assert.ok(out.events.some((e) => e.stageId === "lookup" && e.status === "skipped"));
  assert.match(aiCalls[0]!.body.system, /write all prose in Hindi/);
});

test("critique applies the spoiler filter and reports it", async () => {
  const raw = critiqueJson() as any;
  raw.verdictText = "Solid. The hero dies at the end.";
  aiReply = raw;
  const out = await readStream(await critique(post({ id: 1 })));
  assert.equal(out.result.analysis.critique.verdictText, "Solid.");
  assert.equal(out.result.analysis.notices.length, 1);
});

test("friendly typed errors for bad input, missing film and missing keys", async () => {
  const notFound = await readStream(await critique(post({ query: "nothing" })));
  assert.equal(notFound.error.code, "not_found");
  assert.equal(notFound.error.stage, "lookup");
  const empty = await readStream(await critique(post({ query: "  " })));
  assert.equal(empty.error.code, "invalid_input");
  const malformed = await readStream(await critique(new Request("http://x", { method: "POST", body: "{{" })));
  assert.equal(malformed.error.code, "invalid_input");
  delete process.env.ANTHROPIC_API_KEY;
  const noKey = await readStream(await critique(post({ id: 1 })));
  assert.equal(noKey.error.code, "missing_key");
  assert.match(noKey.error.nextStep, /Settings/);
  assert.match(noKey.error.reference, /-missing_key$/);
  const failed = noKey.events.find((e) => e.stageId === "prepare");
  assert.ok(failed);
  assert.equal(noKey.events.at(-1).status, "failed");
});

test("browser keys take priority over server variables", async () => {
  delete process.env.ANTHROPIC_API_KEY;
  delete process.env.TMDB_API_KEY;
  const out = await readStream(
    await critique(post({ id: 1 }, { "x-tmdb-key": "user-tmdb", "x-ai-provider": "openai", "x-ai-key": "sk-user", "x-ai-model": "gpt-test" })),
  );
  assert.equal(out.error, undefined);
  assert.match(aiCalls[0]!.url, /api\.openai\.com/);
  assert.equal(aiCalls[0]!.headers.authorization, "Bearer sk-user");
  assert.equal(aiCalls[0]!.body.model, "gpt-test");
  assert.ok(out.events.every((e) => e.provider === undefined || e.provider === "openai"));
});

test("an unknown provider from the browser is rejected", async () => {
  const out = await readStream(await critique(post({ id: 1 }, { "x-ai-provider": "nope", "x-ai-key": "k" })));
  assert.equal(out.error.code, "invalid_input");
});

test("server provider selection: openai, mistral, gemini", async () => {
  delete process.env.ANTHROPIC_API_KEY;
  process.env.OPENAI_API_KEY = "sk-openai";
  await readStream(await critique(post({ id: 1 })));
  assert.match(aiCalls[0]!.url, /api\.openai\.com/);
  assert.equal(aiCalls[0]!.body.response_format.type, "json_object");
  process.env.MISTRAL_API_KEY = "m";
  process.env.AI_PROVIDER = "mistral";
  process.env.AI_MODEL = "mistral-small";
  await readStream(await critique(post({ id: 1 })));
  assert.match(aiCalls[1]!.url, /api\.mistral\.ai/);
  assert.equal(aiCalls[1]!.body.model, "mistral-small");
  process.env.GOOGLE_API_KEY = "g";
  process.env.AI_PROVIDER = "gemini";
  delete process.env.AI_MODEL;
  await readStream(await critique(post({ id: 1 })));
  assert.match(aiCalls[2]!.url, /gemini-3\.5-flash:generateContent/);
  assert.equal(aiCalls[2]!.headers["x-goog-api-key"], "g");
});

test("Hugging Face uses the router, the chosen model and requires a model", async () => {
  const headers = { "x-ai-provider": "huggingface", "x-ai-key": "hf_testtoken123" };
  const noModel = await readStream(await critique(post({ id: 1 }, headers)));
  assert.equal(noModel.error.code, "invalid_input");
  assert.match(noModel.error.message, /model/i);
  assert.equal(aiCalls.length, 0);
  const out = await readStream(await critique(post({ id: 1 }, { ...headers, "x-ai-model": "org/model:cheapest" })));
  assert.equal(out.error, undefined);
  assert.equal(aiCalls[0]!.url, "https://router.huggingface.co/v1/chat/completions");
  assert.equal(aiCalls[0]!.headers.authorization, "Bearer hf_testtoken123");
  assert.equal(aiCalls[0]!.body.model, "org/model:cheapest");
  assert.equal(aiCalls[0]!.body.response_format, undefined);
});

test("unreadable output is retried once, shown as a retry, then fails", async () => {
  aiReply = "not json at all";
  const out = await readStream(await critique(post({ id: 1 })));
  assert.equal(out.error.code, "malformed_output");
  assert.equal(aiCalls.length, 2);
  assert.ok(out.events.some((e) => e.stageId === "inference" && e.status === "retrying" && e.retryCount === 1));
});

test("rate limits are retried once and can recover", async () => {
  aiStatus = [429];
  const out = await readStream(await critique(post({ id: 1 })));
  assert.equal(out.error, undefined);
  assert.equal(aiCalls.length, 2);
  assert.ok(out.events.some((e) => e.status === "retrying"));
});

test("auth failures are not retried and never leak the key", async () => {
  aiStatus = [401];
  const res = await critique(post({ id: 1 }));
  const raw = await res.clone().text();
  const out = await readStream(res);
  assert.equal(out.error.code, "auth_failed");
  assert.equal(aiCalls.length, 1);
  assert.doesNotMatch(raw, /sk-ant-test/);
});

test("discover verifies picks on TMDB, reports real progress and drops unknown ones", async () => {
  aiReply = { picks: [{ title: "Arrival", year: "2016", why: "Cerebral." }, { title: "nothing", year: "1999", why: "x" }, { title: "Arrival", year: "2016", why: "dup" }] };
  const out = await readStream(await discover(post({ text: "slow sci-fi" })));
  assert.equal(out.result.picks.length, 1);
  assert.equal(out.result.picks[0].why, "Cerebral.");
  const progress = out.events.filter((e) => e.stageId === "verify" && e.progress !== undefined).map((e) => e.progress);
  assert.equal(progress.at(-1), 1);
  assert.equal((await readStream(await discover(post({ text: "" })))).error.code, "invalid_input");
});

test("ask passes film context, trims history and filters spoilers", async () => {
  aiReply = "Great pacing. Everyone dies in the end.";
  const history = [
    { role: "assistant", content: "stale" },
    { role: "user", content: "hi" },
    { role: "assistant", content: "hello" },
  ];
  const safe = await readStream(await ask(post({ question: "How is it shot?", history, analysis: sampleAnalysis(), spoiler: "none" })));
  assert.equal(safe.result.answer, "Great pacing.");
  const body = aiCalls[0]!.body;
  assert.match(body.system, /FILM: Heat \(1995\)/);
  assert.equal(body.messages[0].role, "user");
  assert.equal(body.messages.length, 3);
  const full = await readStream(await ask(post({ question: "q", spoiler: "full" })));
  assert.match(full.result.answer, /dies/);
  assert.ok(full.events.some((e) => e.stageId === "spoiler" && e.status === "skipped"));
  assert.equal((await readStream(await ask(post({ question: " " })))).error.code, "invalid_input");
});

test("battle reuses supplied analyses and writes a narrative", async () => {
  aiReply = "Both are strong. Overall: depends on mood.";
  const out = await readStream(
    await battle(post({ a: { analysis: sampleAnalysis("Heat") }, b: { analysis: { ...sampleAnalysis("Collateral", { plot: 5 }), movie: { ...sampleAnalysis().movie, id: 5, title: "Collateral" } } }, spoiler: "none" })),
  );
  assert.equal(out.error, undefined);
  assert.match(out.result.narrative, /Overall/);
  assert.equal(aiCalls.length, 1);
  assert.match(aiCalls[0]!.body.messages[0].content, /FILM A: Heat[\s\S]*FILM B: Collateral/);
  assert.ok(out.events.some((e) => e.stageId === "analyze" && e.status === "skipped"));
});

test("battle analyses films it has not seen and rejects identical films", async () => {
  const out = await readStream(await battle(post({ a: { id: 1 }, b: { query: "Arrival" } })));
  assert.equal(out.error, undefined);
  assert.equal(aiCalls.length, 3);
  assert.equal(out.result.a.movie.id, 1);
  const same = await readStream(await battle(post({ a: { id: 1 }, b: { id: 1 } })));
  assert.equal(same.error.code, "invalid_input");
  const missing = await readStream(await battle(post({ a: { id: 1 } })));
  assert.equal(missing.error.code, "invalid_input");
});

test("connection test reports latency, token usage and listing status", async () => {
  aiReply = "OK";
  restore();
  restore = mockFetch((url, init) => {
    if (url.includes("/v1/models")) return { data: [{ id: "claude-sonnet-5-5" }] };
    aiCalls.push({ url, body: JSON.parse(String(init?.body)), headers: init?.headers as Record<string, string> });
    return { content: [{ type: "text", text: "OK" }], usage: { input_tokens: 9, output_tokens: 1 } };
  });
  const out = await readStream(await connection(post({})));
  assert.equal(out.error, undefined);
  assert.equal(out.result.ok, true);
  assert.equal(out.result.modelListed, true);
  assert.equal(out.result.inputTokens, 9);
  assert.equal(aiCalls[0]!.body.max_tokens, 64);
});

test("connection test surfaces a rejected key and an empty reply honestly", async () => {
  restore();
  restore = mockFetch(() => new Response("{}", { status: 401 }));
  assert.equal((await readStream(await connection(post({})))).error.code, "auth_failed");
  restore();
  restore = mockFetch((url) => (url.includes("/v1/models") ? { data: [] } : { content: [{ type: "text", text: "" }] }));
  assert.equal((await readStream(await connection(post({})))).error.code, "empty_response");
});

test("Hugging Face connection test skips the credential stage instead of faking it", async () => {
  restore();
  restore = mockFetch(() => ({ choices: [{ message: { content: "OK" } }] }));
  const out = await readStream(
    await connection(post({}, { "x-ai-provider": "huggingface", "x-ai-key": "hf_abcdef123456", "x-ai-model": "org/m" })),
  );
  assert.equal(out.result.ok, true);
  assert.equal(out.result.modelListed, null);
  assert.ok(out.events.some((e) => e.stageId === "auth" && e.status === "skipped"));
});

test("a slow provider ends the run with a timeout, not a hang", async () => {
  restore();
  restore = mockFetch((url, init) => (url.includes("themoviedb") ? tmdbData(url) : new Promise((_, reject) => init?.signal?.addEventListener("abort", () => reject(init.signal!.reason)))));
  const original = AbortSignal.timeout;
  AbortSignal.timeout = ((ms: number) => original.call(AbortSignal, ms > 5000 ? 150 : ms)) as typeof AbortSignal.timeout;
  const keepAlive = setInterval(() => {}, 20);
  try {
    const out = await readStream(await critique(post({ id: 1 })));
    assert.equal(out.error.code, "timeout");
    assert.equal(out.events.at(-1).status, "timed_out");
  } finally {
    clearInterval(keepAlive);
    AbortSignal.timeout = original;
  }
});

test("models endpoint lists Hugging Face router models without a key", async () => {
  restore();
  let auth = "unset";
  restore = mockFetch((url, init) => {
    auth = String((init?.headers as Record<string, string> | undefined)?.authorization);
    return {
      data: [
        { id: "org/dead", providers: [{ provider: "x", status: "offline" }] },
        { id: "org/live", owned_by: "org", providers: [{ provider: "y", status: "live", context_length: 32768, supports_structured_output: true }] },
      ],
    };
  });
  const res = await models(new Request("http://x/api/models?provider=huggingface"));
  const data: any = await res.json();
  assert.equal(data.source, "provider");
  assert.equal(data.models[0].id, "org/live");
  assert.equal(data.models[0].recommended, true);
  assert.equal(data.models[0].contextLength, 32768);
  assert.equal(data.models[1].compatible, false);
  assert.equal(auth, "undefined");
  assert.equal((await models(new Request("http://x/api/models?provider=nope"))).status, 400);
});

test("models endpoint falls back to a labelled default when listing fails", async () => {
  restore();
  restore = mockFetch(() => new Response("{}", { status: 401 }));
  const res = await models(new Request("http://x/api/models?provider=openai", { headers: { "x-ai-provider": "openai", "x-ai-key": "sk-bad-key-123" } }));
  const data: any = await res.json();
  assert.equal(data.source, "default");
  assert.equal(data.models[0].id, "gpt-4o-mini");
  assert.match(data.warning, /rejected/);
  assert.doesNotMatch(JSON.stringify(data), /sk-bad-key-123/);
});
