import { PROVIDERS, isProviderId } from "../shared/providers.js";
import { compareScores, dimensionScores } from "../shared/scoring.js";
import type { Analysis, BattleResponse, ChatMessage, ConnectionResult, CritiqueResponse, Movie, MovieDetails, Pick, SpoilerLevel } from "../shared/types.js";
import { generateJson, generateText, infer, resolveConfig, type AiConfig, type Env, type Inference } from "./ai.js";
import { comparisonContext, filmContext, isAnalysis } from "./context.js";
import { AppError } from "./errors.js";
import { cleanText, readOptions } from "./http.js";
import { requestKeys } from "./keys.js";
import { ADAPTERS } from "./providers/index.js";
import { generateCritique, parseCritique } from "./critique.js";
import type { OperationContext, Tracker } from "./pipeline.js";
import { askSystem, compareSystem, discoverSystem } from "./prompts.js";
import { enforce, stripSpoilers } from "./spoilers.js";
import { chooseBest, findMovie, getDetails, getSimilar, requireTmdb, searchMovies } from "./tmdb.js";

const DISCOVER_COUNT = 6;
const HISTORY_LIMIT = 8;

const seconds = (ms: number) => `${(ms / 1000).toFixed(1)}s`;

function usage(result: Inference): string {
  const parts = [`${PROVIDERS[result.provider].label} · ${result.model}`, seconds(result.latencyMs)];
  if (result.inputTokens !== undefined && result.outputTokens !== undefined) parts.push(`${result.inputTokens} in / ${result.outputTokens} out tokens`);
  return parts.join(" · ");
}

function prepare(t: Tracker, needsTmdb: boolean): Promise<AiConfig> {
  return t.stage(
    "prepare",
    "Checking AI settings",
    () => {
      const config = resolveConfig();
      if (needsTmdb) requireTmdb();
      t.setModel(config.provider, config.model);
      return config;
    },
    (config) => `${PROVIDERS[config.provider].label} · ${config.model}`,
  );
}

const retryNote = (t: Tracker, stage: string) => (error: AppError) => t.retrying(stage, `${error.message} Retrying.`);

function filmId(value: unknown): number {
  return Number.isInteger(value) && (value as number) > 0 ? (value as number) : 0;
}

export async function critiqueOperation({ body, t, env }: OperationContext): Promise<CritiqueResponse> {
  const request = await t.stage(
    "validate",
    "Checking your request",
    () => {
      const id = filmId(body.id);
      const query = cleanText(body.query, 120);
      if (!id && !query) throw new AppError("invalid_input", { message: "Enter a film name first." });
      return { id, query, ...readOptions(body) };
    },
    "Request is valid",
  );
  const config = await prepare(t, true);

  let id = request.id;
  let alternatives: Movie[] = [];
  if (id) t.skip("lookup", "Film already selected");
  else {
    const found = await t.stage(
      "lookup",
      "Searching TMDB",
      async () => {
        const match = await findMovie(request.query);
        if (!match) {
          throw new AppError("not_found", {
            message: "No film matched your search.",
            nextStep: "Check the spelling or add the year, like “Heat (1995)”.",
          });
        }
        return match;
      },
      (match) => `Matched ${match.best.title}${match.best.year ? ` (${match.best.year})` : ""}`,
    );
    id = found.best.id;
    alternatives = found.alternatives;
  }

  const { movie, similar } = await t.stage(
    "details",
    "Fetching cast, crew and similar films",
    async () => {
      const [details, related] = await Promise.all([getDetails(id), getSimilar(id).catch(() => [])]);
      return { movie: details, similar: related };
    },
    ({ movie: m }) => `${m.title}${m.year ? ` (${m.year})` : ""}`,
  );

  const generated = await t.stage(
    "inference",
    `Waiting for ${config.model}`,
    () => generateCritique(movie, request.spoiler, request.language, { ...env, config, onRetry: retryNote(t, "inference") }),
    usage,
  );
  const critique = await t.stage("validate_output", "Checking the AI response", () => parseCritique(generated.data), "Response is usable");
  const removed = await t.stage(
    "spoiler",
    "Applying spoiler protection",
    () => enforce(critique, request.spoiler),
    (n) => (n ? `Removed ${n} sentence(s)` : "No changes needed"),
  );

  return t.stage(
    "finalize",
    "Preparing results",
    () => ({
      analysis: {
        movie,
        critique,
        similar,
        spoiler: request.spoiler,
        language: request.language,
        notices: removed ? [`${removed} sentence(s) were removed by the spoiler filter to keep this analysis safe.`] : [],
        createdAt: Date.now(),
        generatedBy: { provider: config.provider, model: config.model },
      },
      alternatives,
    }),
    "Ready",
  );
}

export async function discoverOperation({ body, t, env }: OperationContext): Promise<{ picks: Pick[] }> {
  const text = await t.stage(
    "validate",
    "Checking your request",
    () => {
      const value = cleanText(body.text, 300);
      if (!value) throw new AppError("invalid_input", { message: "Describe a film, mood or genre first." });
      return value;
    },
    "Request is valid",
  );
  const config = await prepare(t, true);

  const generated = await t.stage(
    "inference",
    `Waiting for ${config.model}`,
    () =>
      generateJson({
        ...env,
        config,
        system: discoverSystem(DISCOVER_COUNT),
        messages: [{ role: "user", content: `User input: ${text}` }],
        onRetry: retryNote(t, "inference"),
      }),
    usage,
  );
  const suggestions = await t.stage(
    "validate_output",
    "Checking the AI response",
    () => {
      const items = (Array.isArray(generated.data.picks) ? generated.data.picks : []).slice(0, DISCOVER_COUNT) as Record<string, unknown>[];
      if (!items.length) throw new AppError("malformed_output", { message: "The AI did not suggest any films." });
      return items;
    },
    (items) => `${items.length} suggestion(s)`,
  );

  const picks = await t.stage(
    "verify",
    "Verifying films on TMDB",
    async () => {
      let done = 0;
      const results = await Promise.allSettled(
        suggestions.map(async (item) => {
          const title = cleanText(item.title, 120);
          const year = /^\d{4}$/.test(String(item.year)) ? String(item.year) : "";
          try {
            const found = chooseBest(await searchMovies(title, year), title, year);
            return found ? { ...found.best, why: cleanText(item.why, 140) } : null;
          } finally {
            done += 1;
            t.progress("verify", `Checked ${done} of ${suggestions.length}`, done / suggestions.length);
          }
        }),
      );
      const failures = results.filter((r): r is PromiseRejectedResult => r.status === "rejected");
      const seen = new Set<number>();
      const verified: Pick[] = [];
      for (const result of results) {
        if (result.status !== "fulfilled" || !result.value || seen.has(result.value.id)) continue;
        seen.add(result.value.id);
        verified.push(result.value);
      }
      if (!verified.length && failures[0]) throw failures[0].reason;
      if (!verified.length) throw new AppError("not_found", { message: "None of the suggested films could be verified.", nextStep: "Try rephrasing." });
      return verified;
    },
    (verified) => `${verified.length} of ${suggestions.length} verified`,
  );

  return t.stage("finalize", "Preparing results", () => ({ picks }), "Ready");
}

function readHistory(value: unknown): ChatMessage[] {
  const items = (Array.isArray(value) ? value : [])
    .filter((m): m is ChatMessage => (m?.role === "user" || m?.role === "assistant") && typeof m.content === "string")
    .slice(-HISTORY_LIMIT)
    .map((m) => ({ role: m.role, content: m.content.slice(0, 1500) }));
  while (items[0]?.role === "assistant") items.shift();
  return items;
}

export async function askOperation({ body, t, env }: OperationContext): Promise<{ answer: string }> {
  const request = await t.stage(
    "validate",
    "Checking your question",
    () => {
      const question = cleanText(body.question, 800);
      if (!question) throw new AppError("invalid_input", { message: "Type a question first." });
      return { question, ...readOptions(body) };
    },
    "Question is valid",
  );
  const config = await prepare(t, false);

  const context = isAnalysis(body.analysis) ? filmContext(body.analysis, request.spoiler) : "";
  const generated = await t.stage(
    "inference",
    `Waiting for ${config.model}`,
    () =>
      generateText({
        ...env,
        config,
        system: askSystem(request.spoiler, request.language, context),
        messages: [...readHistory(body.history), { role: "user", content: request.question }],
        onRetry: retryNote(t, "inference"),
      }),
    usage,
  );

  let answer = generated.text;
  if (request.spoiler === "full") t.skip("spoiler", "Full spoilers selected");
  else {
    answer = await t.stage(
      "spoiler",
      "Applying spoiler protection",
      () => stripSpoilers(generated.text, false).text,
      "Checked",
    );
  }
  return t.stage("finalize", "Preparing results", () => ({ answer }), "Ready");
}

interface BattleTarget {
  analysis: Analysis | null;
  id: number;
  query: string;
}

function readTarget(value: unknown): BattleTarget {
  const item = (typeof value === "object" && value !== null ? value : {}) as Record<string, unknown>;
  const analysis = isAnalysis(item.analysis) ? item.analysis : null;
  return { analysis, id: filmId(item.id), query: cleanText(item.query, 120) };
}

async function resolveFilm(target: BattleTarget): Promise<{ movie: MovieDetails; similar: Movie[] }> {
  if (target.analysis) return { movie: target.analysis.movie, similar: target.analysis.similar };
  let id = target.id;
  if (!id) {
    const found = await findMovie(target.query);
    if (!found) throw new AppError("not_found", { message: `No film matched “${target.query}”.`, nextStep: "Check the spelling or add the year." });
    id = found.best.id;
  }
  const [movie, similar] = await Promise.all([getDetails(id), getSimilar(id).catch(() => [])]);
  return { movie, similar };
}

async function analyseFilm(
  film: { movie: MovieDetails; similar: Movie[] },
  spoiler: SpoilerLevel,
  language: string,
  config: AiConfig,
  env: Env,
  onRetry: (error: AppError) => void,
): Promise<Analysis> {
  const generated = await generateCritique(film.movie, spoiler, language, { ...env, config, onRetry });
  const critique = parseCritique(generated.data);
  const removed = enforce(critique, spoiler);
  return {
    movie: film.movie,
    critique,
    similar: film.similar,
    spoiler,
    language,
    notices: removed ? [`${removed} sentence(s) were removed by the spoiler filter to keep this analysis safe.`] : [],
    createdAt: Date.now(),
    generatedBy: { provider: config.provider, model: config.model },
  };
}

export async function battleOperation({ body, t, env }: OperationContext): Promise<BattleResponse> {
  const request = await t.stage(
    "validate",
    "Checking your request",
    () => {
      const targets = [readTarget(body.a), readTarget(body.b)] as const;
      if (targets.some((x) => !x.analysis && !x.id && !x.query)) {
        throw new AppError("invalid_input", { message: "Pick two films to compare." });
      }
      return { targets, ...readOptions(body) };
    },
    "Request is valid",
  );
  const config = await prepare(t, true);

  const films = await t.stage(
    "resolve",
    "Finding both films",
    async () => {
      let done = 0;
      const resolved = await Promise.all(
        request.targets.map(async (target) => {
          const film = await resolveFilm(target);
          done += 1;
          t.progress("resolve", `Found ${done} of 2`, done / 2);
          return film;
        }),
      );
      if (resolved[0]!.movie.id === resolved[1]!.movie.id) {
        throw new AppError("invalid_input", { message: "Pick two different films.", nextStep: "Choose a different second film." });
      }
      return resolved as [typeof resolved[0], typeof resolved[0]];
    },
    ([a, b]) => `${a.movie.title} vs ${b.movie.title}`,
  );

  const pending = request.targets.map((target, index) => ({ target, index })).filter(({ target }) => !target.analysis);
  const analyses: [Analysis | null, Analysis | null] = [request.targets[0].analysis, request.targets[1].analysis];
  if (!pending.length) t.skip("analyze", "Both analyses were already available");
  else {
    await t.stage(
      "analyze",
      `Analysing ${pending.length} film(s)`,
      async () => {
        let done = 0;
        await Promise.all(
          pending.map(async ({ index }) => {
            analyses[index] = await analyseFilm(films[index]!, request.spoiler, request.language, config, env, retryNote(t, "analyze"));
            done += 1;
            t.progress("analyze", `Finished ${done} of ${pending.length}`, done / pending.length);
          }),
        );
      },
      `${pending.length} analysis complete`,
    );
  }
  const [a, b] = analyses as [Analysis, Analysis];

  const comparison = await t.stage("compare", "Comparing scores", () => compareScores(dimensionScores(a.critique), dimensionScores(b.critique)), "Scores compared");

  const generated = await t.stage(
    "narrative",
    `Waiting for ${config.model}`,
    () =>
      generateText({
        ...env,
        config,
        system: compareSystem(request.spoiler, request.language),
        messages: [{ role: "user", content: comparisonContext(a, b, comparison) }],
        onRetry: retryNote(t, "narrative"),
      }),
    usage,
  );
  const narrative = request.spoiler === "full" ? generated.text : stripSpoilers(generated.text, false).text;

  return t.stage("finalize", "Preparing results", () => ({ a, b, narrative }), "Ready");
}

export async function connectionOperation({ t, env }: OperationContext): Promise<ConnectionResult> {
  await t.stage(
    "validate",
    "Checking settings",
    () => {
      const sent = requestKeys();
      if (sent.ai && !isProviderId(sent.provider)) throw new AppError("invalid_input", { message: "Choose an AI provider first." });
    },
    "Settings are valid",
  );
  const config = await prepare(t, false);

  let modelListed: boolean | null = null;
  if (config.provider === "huggingface") {
    t.skip("auth", "Hugging Face checks the token when the model is called");
  } else {
    modelListed = await t.stage(
      "auth",
      "Checking the key with the provider",
      async () => {
        try {
          const models = await ADAPTERS[config.provider].list({ key: config.key, signal: env.signal, secrets: [config.key] });
          return models.length ? models.some((m) => m.id === config.model) : null;
        } catch (error) {
          if (error instanceof AppError && error.code === "permission_denied") return null;
          throw error;
        }
      },
      (listed) => (listed === null ? "Key accepted, or its permissions do not allow listing models" : listed ? "Key accepted and model is listed" : "Key accepted, but the model is not in the provider's list"),
    );
  }

  const result = await t.stage(
    "inference",
    `Sending a test message to ${config.model}`,
    async () => {
      const reply = await infer({
        ...env,
        config,
        system: "You are a connectivity check. Reply with the single word OK.",
        messages: [{ role: "user", content: "Ping" }],
        maxTokens: 64,
        onRetry: retryNote(t, "inference"),
      });
      if (!reply.text.trim()) throw new AppError("empty_response", { message: "The model connected but returned an empty reply." });
      return reply;
    },
    usage,
  );

  return t.stage(
    "finalize",
    "Summarising",
    () => ({
      ok: true as const,
      provider: config.provider,
      model: config.model,
      latencyMs: result.latencyMs,
      reply: result.text.trim().slice(0, 80),
      modelListed,
      ...(result.inputTokens !== undefined ? { inputTokens: result.inputTokens } : {}),
      ...(result.outputTokens !== undefined ? { outputTokens: result.outputTokens } : {}),
      checkedAt: Date.now(),
    }),
    "Connection works",
  );
}
