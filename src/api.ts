import type { ModelCatalogue } from "../shared/providers";
import type { ChatMessage, Analysis, ListKind, Movie, MovieListResponse, SpoilerLevel } from "../shared/types";
import { EMPTY_CREDENTIALS, authHeaders, type Credentials } from "./keys";

export interface Options {
  spoiler: SpoilerLevel;
  language: string;
}

export interface Target {
  id?: number;
  query?: string;
}

export interface Availability {
  tmdb: boolean;
  ai: boolean;
}

export type { ChatMessage, Analysis };

let credentials: Credentials = EMPTY_CREDENTIALS;

export function setCredentials(next: Credentials): void {
  credentials = next;
}

export const savedHeaders = (): Record<string, string> => authHeaders(credentials);

async function request<T>(path: string, init: RequestInit = {}, headers: Record<string, string> = savedHeaders()): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { ...init, headers: { ...headers, ...(init.headers as Record<string, string> | undefined) } });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new Error("Network error. Check your connection and try again.");
  }
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const body = data as { error?: string; nextStep?: string } | null;
    throw new Error(body?.error ? `${body.error}${body.nextStep ? ` ${body.nextStep}` : ""}` : "Request failed. Please try again.");
  }
  return data as T;
}

export const api = {
  status: () => request<Availability>("/api/status", { cache: "no-store" }),
  search: (query: string, signal?: AbortSignal) => request<{ items: Movie[] }>(`/api/movies?q=${encodeURIComponent(query)}`, { signal }),
  list: (kind: ListKind, page: number) => request<MovieListResponse>(`/api/movies?list=${kind}&page=${page}`),
  models: (draft: Credentials, signal?: AbortSignal) =>
    request<ModelCatalogue>(
      `/api/models?provider=${draft.provider}`,
      { cache: "no-store", ...(signal ? { signal } : {}) },
      authHeaders({ ...draft, tmdb: "" }),
    ),
};
