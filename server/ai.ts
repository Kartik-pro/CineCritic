import { MODEL_ID_PATTERN, PROVIDER_IDS, PROVIDERS, isProviderId, type ProviderId } from "../shared/providers.js";
import type { ChatMessage } from "../shared/types.js";
import { AppError, toAppError } from "./errors.js";
import { requestKeys } from "./keys.js";
import { ADAPTERS } from "./providers/index.js";

const SERVER_ORDER: readonly ProviderId[] = ["anthropic", "openai", "gemini", "mistral", "huggingface"];
const CALL_TIMEOUT_MS = 50_000;
const MIN_REMAINING_MS = 1_500;
const BACKOFF_MS = 800;
const MAX_ATTEMPTS = 2;
const RETRYABLE: readonly string[] = ["rate_limited", "provider_unavailable", "network"];

export interface AiConfig {
  provider: ProviderId;
  key: string;
  model: string;
  viaRequest: boolean;
}

export interface Env {
  signal: AbortSignal;
  deadline: number;
}

export interface InferOptions extends Env {
  system: string;
  messages: ChatMessage[];
  json?: boolean;
  maxTokens?: number;
  config?: AiConfig;
  onRetry?: (error: AppError) => void;
}

export interface Inference {
  text: string;
  provider: ProviderId;
  model: string;
  latencyMs: number;
  inputTokens?: number;
  outputTokens?: number;
}

const serverKey = (provider: ProviderId): string => process.env[PROVIDERS[provider].envVar]?.trim() ?? "";

export const hasServerAiKey = (): boolean => PROVIDER_IDS.some((p) => !!serverKey(p));

function finish(provider: ProviderId, key: string, requested: string, viaRequest: boolean): AiConfig {
  const meta = PROVIDERS[provider];
  const model = requested || meta.defaultModel;
  if (!model) {
    throw new AppError("invalid_input", {
      message: `Choose a ${meta.label} model before continuing.`,
      nextStep: "Open Settings, pick a model and save it as your default.",
    });
  }
  if (!MODEL_ID_PATTERN.test(model)) {
    throw new AppError("invalid_input", { message: "The model name contains unsupported characters.", nextStep: "Pick a model from the list in Settings." });
  }
  return { provider, key, model, viaRequest };
}

export function resolveConfig(): AiConfig {
  const sent = requestKeys();
  if (sent.ai) {
    if (!isProviderId(sent.provider)) {
      throw new AppError("invalid_input", { message: "Choose an AI provider in Settings.", nextStep: "Open Settings and select a provider." });
    }
    return finish(sent.provider, sent.ai, sent.model, true);
  }
  const requested = process.env.AI_PROVIDER?.trim().toLowerCase();
  const candidates = isProviderId(requested) ? [requested] : SERVER_ORDER;
  for (const provider of candidates) {
    const key = serverKey(provider);
    if (key) return finish(provider, key, process.env.AI_MODEL?.trim() ?? "", false);
  }
  throw new AppError("missing_key", { message: "No AI API key is configured.", nextStep: "Add an AI key in Settings." });
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) return reject(signal.reason);
    const onAbort = () => {
      clearTimeout(timer);
      reject(signal.reason);
    };
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

export async function infer(options: InferOptions): Promise<Inference> {
  const config = options.config ?? resolveConfig();
  const adapter = ADAPTERS[config.provider];
  for (let attempt = 1; ; attempt++) {
    const remaining = options.deadline - Date.now();
    if (remaining < MIN_REMAINING_MS) throw new AppError("timeout");
    const started = Date.now();
    try {
      const result = await adapter.generate({
        key: config.key,
        model: config.model,
        system: options.system,
        messages: options.messages,
        json: options.json ?? false,
        ...(options.maxTokens !== undefined ? { maxTokens: options.maxTokens } : {}),
        signal: options.signal,
        timeoutMs: Math.min(CALL_TIMEOUT_MS, remaining),
        secrets: [config.key],
      });
      return {
        text: result.text,
        provider: config.provider,
        model: config.model,
        latencyMs: Date.now() - started,
        ...(result.inputTokens !== undefined ? { inputTokens: result.inputTokens } : {}),
        ...(result.outputTokens !== undefined ? { outputTokens: result.outputTokens } : {}),
      };
    } catch (error) {
      const app = toAppError(error, "inference", [config.key]);
      if (!RETRYABLE.includes(app.code) || attempt >= MAX_ATTEMPTS) throw app;
      options.onRetry?.(app);
      await sleep(BACKOFF_MS, options.signal);
    }
  }
}

export function extractJson(text: string): unknown {
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start < 0 || end <= start) throw new Error("no json");
  return JSON.parse(text.slice(start, end + 1));
}

export async function generateText(options: InferOptions): Promise<Inference> {
  for (let attempt = 0; attempt < 2; attempt++) {
    const result = await infer(options);
    const text = result.text.trim();
    if (text) return { ...result, text };
    if (attempt === 0) options.onRetry?.(new AppError("empty_response"));
  }
  throw new AppError("empty_response");
}

export async function generateJson(options: InferOptions): Promise<Inference & { data: Record<string, unknown> }> {
  for (let attempt = 0; attempt < 2; attempt++) {
    const result = await infer({ ...options, json: true });
    try {
      const parsed = extractJson(result.text);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return { ...result, data: parsed as Record<string, unknown> };
    } catch {
      if (attempt === 1) throw new AppError("malformed_output");
    }
    if (attempt === 0) options.onRetry?.(new AppError("malformed_output"));
  }
  throw new AppError("malformed_output");
}
