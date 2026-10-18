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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
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
