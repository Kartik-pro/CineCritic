import type {
  Analysis,
  ChatMessage,
  CritiqueResponse,
  ListKind,
  Movie,
  MovieListResponse,
  Pick,
  SpoilerLevel,
} from "../shared/types";

export interface Options {
  spoiler: SpoilerLevel;
  language: string;
}

export interface Target {
  id?: number;
  query?: string;
}

export const AI_PROVIDERS = [
  { id: "gemini", label: "Google Gemini", model: "gemini-3.5-flash" },
  { id: "openai", label: "OpenAI", model: "gpt-4o-mini" },
  { id: "anthropic", label: "Anthropic", model: "claude-sonnet-5-5" },
  { id: "mistral", label: "Mistral", model: "mistral-large-latest" },
] as const;

export type AiProvider = (typeof AI_PROVIDERS)[number]["id"];

export interface StoredKeys {
  tmdb: string;
  provider: AiProvider;
  ai: string;
  model: string;
}

export const EMPTY_KEYS: StoredKeys = { tmdb: "", provider: "gemini", ai: "", model: "" };

export interface Availability {
  tmdb: boolean;
  ai: boolean;
}

let keys: StoredKeys = EMPTY_KEYS;

export function setApiKeys(next: StoredKeys): void {
  keys = next;
}

function keyHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  if (keys.tmdb) headers["x-tmdb-key"] = keys.tmdb;
  if (keys.ai) {
    headers["x-ai-key"] = keys.ai;
    headers["x-ai-provider"] = keys.provider;
    if (keys.model) headers["x-ai-model"] = keys.model;
  }
  return headers;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { ...init, headers: { ...keyHeaders(), ...(init?.headers as Record<string, string> | undefined) } });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new Error("Network error. Check your connection and try again.");
  }
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const message = (data as { error?: string } | null)?.error;
    throw new Error(message ?? "Request failed. Please try again.");
  }
  return data as T;
}

const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  status: () => request<Availability>("/api/status", { cache: "no-store" }),
  search: (query: string, signal?: AbortSignal) =>
    request<{ items: Movie[] }>(`/api/movies?q=${encodeURIComponent(query)}`, { signal }),
  list: (kind: ListKind, page: number) => request<MovieListResponse>(`/api/movies?list=${kind}&page=${page}`),
  critique: (target: Target, options: Options) => post<CritiqueResponse>("/api/critique", { ...target, ...options }),
  discover: (text: string) => post<{ picks: Pick[] }>("/api/discover", { text }),
  ask: (question: string, history: ChatMessage[], analysis: Analysis | null, options: Options) =>
    post<{ answer: string }>("/api/ask", { question, history, analysis, ...options }),
  compare: (a: Analysis, b: Analysis, options: Options) =>
    post<{ narrative: string }>("/api/compare", { a, b, ...options }),
};
