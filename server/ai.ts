import type { ChatMessage } from "../shared/types";
import { HttpError } from "./http";
import { requestKeys } from "./keys";

type Provider = "anthropic" | "openai" | "gemini" | "mistral";

const PROVIDERS: Record<Provider, { env: string; model: string }> = {
  anthropic: { env: "ANTHROPIC_API_KEY", model: "claude-sonnet-5-5" },
  openai: { env: "OPENAI_API_KEY", model: "gpt-4o-mini" },
  gemini: { env: "GOOGLE_API_KEY", model: "gemini-3.5-flash" },
  mistral: { env: "MISTRAL_API_KEY", model: "mistral-large-latest" },
};

const OPENAI_COMPATIBLE: Record<"openai" | "mistral", string> = {
  openai: "https://api.openai.com/v1/chat/completions",
  mistral: "https://api.mistral.ai/v1/chat/completions",
};

export interface GenerateOptions {
  system: string;
  messages: ChatMessage[];
  json?: boolean;
}

export function hasServerAiKey(): boolean {
  return (Object.keys(PROVIDERS) as Provider[]).some((p) => !!process.env[PROVIDERS[p].env]?.trim());
}

function configured(): { provider: Provider; key: string; model: string } {
  const sent = requestKeys();
  if (sent.ai) {
    if (!(sent.provider in PROVIDERS)) throw new HttpError(400, "Choose an AI provider in Settings.");
    const provider = sent.provider as Provider;
    return { provider, key: sent.ai, model: sent.model || PROVIDERS[provider].model };
  }
  const requested = process.env.AI_PROVIDER?.trim().toLowerCase();
  const order = Object.keys(PROVIDERS) as Provider[];
  const candidates = requested && requested in PROVIDERS ? [requested as Provider] : order;
  for (const provider of candidates) {
    const key = process.env[PROVIDERS[provider].env]?.trim();
    if (key) return { provider, key, model: process.env.AI_MODEL?.trim() || PROVIDERS[provider].model };
  }
  throw new HttpError(401, "Add an AI API key in Settings to continue.");
}

async function send(url: string, headers: Record<string, string>, body: unknown): Promise<any> {
  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json", ...headers },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(50_000),
    });
  } catch {
    throw new HttpError(504, "The AI provider did not respond in time. Please try again.");
  }
  if (response.ok) return response.json();
  if (response.status === 401 || response.status === 403)
    throw new HttpError(401, "The AI provider rejected the API key. Check it in Settings.");
  if (response.status === 404) throw new HttpError(400, "That AI model was not found. Check the model name in Settings.");
  if (response.status === 429) throw new HttpError(429, "The AI provider is rate-limiting requests. Try again shortly.");
  throw new HttpError(503, "The AI provider is temporarily unavailable. Please try again.");
}

async function call(opts: GenerateOptions): Promise<string> {
  const { provider, key, model } = configured();

  if (provider === "anthropic") {
    const data = await send(
      "https://api.anthropic.com/v1/messages",
      { "x-api-key": key, "anthropic-version": "2023-06-01" },
      { model, max_tokens: 4096, system: opts.system, messages: opts.messages },
    );
    return (data.content ?? []).map((block: any) => (block.type === "text" ? block.text : "")).join("");
  }

  if (provider === "gemini") {
    const data = await send(
      `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent`,
      { "x-goog-api-key": key },
      {
        systemInstruction: { parts: [{ text: opts.system }] },
        contents: opts.messages.map((m) => ({ role: m.role === "assistant" ? "model" : "user", parts: [{ text: m.content }] })),
        generationConfig: opts.json ? { responseMimeType: "application/json" } : {},
      },
    );
    const parts: any[] = data.candidates?.[0]?.content?.parts ?? [];
    return parts.filter((p) => !p.thought).map((p) => p.text ?? "").join("");
  }

  const data = await send(
    OPENAI_COMPATIBLE[provider],
    { authorization: `Bearer ${key}` },
    {
      model,
      messages: [{ role: "system", content: opts.system }, ...opts.messages],
      ...(opts.json ? { response_format: { type: "json_object" } } : {}),
    },
  );
  const content = data.choices?.[0]?.message?.content;
  return typeof content === "string" ? content : "";
}

async function withRetry<T>(fn: () => Promise<T>): Promise<T> {
  try {
    return await fn();
  } catch (error) {
    if (error instanceof HttpError && (error.status === 503 || error.status === 429)) {
      await new Promise((resolve) => setTimeout(resolve, 800));
      return fn();
    }
    throw error;
  }
}

export async function generateText(opts: GenerateOptions): Promise<string> {
  const text = (await withRetry(() => call(opts))).trim();
  if (!text) throw new HttpError(502, "The AI returned an empty response. Please try again.");
  return text;
}

export function extractJson(text: string): unknown {
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start < 0 || end <= start) throw new Error("no json");
  return JSON.parse(text.slice(start, end + 1));
}

export async function generateJson(opts: GenerateOptions): Promise<Record<string, unknown>> {
  for (let attempt = 0; attempt < 2; attempt++) {
    const text = await withRetry(() => call({ ...opts, json: true }));
    try {
      const parsed = extractJson(text);
      if (parsed && typeof parsed === "object") return parsed as Record<string, unknown>;
    } catch {
      continue;
    }
  }
  throw new HttpError(502, "The AI returned an unreadable response. Please try again.");
}
