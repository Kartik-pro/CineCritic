import type { ListKind, Movie, MovieDetails, MovieListResponse } from "../shared/types";
import { HttpError } from "./http";
import { requestKeys } from "./keys";

const API = "https://api.themoviedb.org/3";
const IMAGE = "https://image.tmdb.org/t/p";

type Raw = Record<string, any>;

async function tmdb(path: string, params: Record<string, string | number> = {}): Promise<Raw> {
  const key = requestKeys().tmdb || process.env.TMDB_API_KEY?.trim();
  if (!key) throw new HttpError(401, "Add your TMDB API key in Settings to continue.");
  const url = new URL(API + path);
  const headers: Record<string, string> = {};
  if (key.startsWith("eyJ")) headers.Authorization = `Bearer ${key}`;
  else url.searchParams.set("api_key", key);
  for (const [name, value] of Object.entries(params)) url.searchParams.set(name, String(value));

  let response: Response;
  try {
    response = await fetch(url, { headers, signal: AbortSignal.timeout(8000) });
  } catch {
    throw new HttpError(502, "Could not reach TMDB. Please try again.");
  }
  if (response.status === 401) throw new HttpError(401, "TMDB rejected the API key. Check it in Settings.");
  if (response.status === 404) throw new HttpError(404, "Film not found on TMDB.");
  if (response.status === 429) throw new HttpError(429, "TMDB is rate-limiting requests. Try again shortly.");
  if (!response.ok) throw new HttpError(502, "TMDB returned an error. Please try again.");
  return (await response.json()) as Raw;
}

const image = (path: unknown, size: string) => (typeof path === "string" && path ? `${IMAGE}/${size}${path}` : "");

function toMovie(item: Raw): Movie | null {
  if (!item?.id || !item.title) return null;
  const votes = Number(item.vote_count) || 0;
  const average = Number(item.vote_average) || 0;
  return {
    id: Number(item.id),
    title: String(item.title),
    year: String(item.release_date ?? "").slice(0, 4),
    overview: String(item.overview ?? ""),
    poster: image(item.poster_path, "w342"),
    rating: votes > 0 && average > 0 ? Math.round(average * 10) / 10 : null,
  };
}

function toMovies(results: unknown): Movie[] {
  return (Array.isArray(results) ? results : []).map(toMovie).filter((m): m is Movie => m !== null);
}

export function normalizeTitle(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9 ]+/g, "")
    .replace(/^(the|a|an) /, "")
    .replace(/\s+/g, " ")
    .trim();
}

export function parseTitleYear(text: string): { title: string; year: string } {
  const match = text.trim().match(/^(.+?)\s*\((\d{4})\)$/);
  return match?.[1] && match[2] ? { title: match[1].trim(), year: match[2] } : { title: text.trim(), year: "" };
}

export async function searchMovies(query: string, year = "", page = 1): Promise<Movie[]> {
  const params: Record<string, string | number> = { query, include_adult: "false", page };
  if (year) params.year = year;
  const data = await tmdb("/search/movie", params);
  return toMovies(data.results);
}

export function chooseBest(candidates: Movie[], title: string, year = ""): { best: Movie; alternatives: Movie[] } | null {
  if (!candidates.length) return null;
  const wanted = normalizeTitle(title);
  const rank = (m: Movie) => (normalizeTitle(m.title) === wanted ? 2 : 0) + (year && m.year === year ? 1 : 0);
  let best = candidates[0]!;
  let bestRank = rank(best);
  for (const m of candidates) {
    const r = rank(m);
    if (r > bestRank) {
      best = m;
      bestRank = r;
    }
  }
  const alternatives = candidates
    .filter((m) => m.id !== best.id && normalizeTitle(m.title) === normalizeTitle(best.title) && m.year !== best.year)
    .sort((a, b) => b.year.localeCompare(a.year))
    .slice(0, 3);
  return { best, alternatives };
}

export async function findMovie(query: string): Promise<{ best: Movie; alternatives: Movie[] } | null> {
  const { title, year } = parseTitleYear(query);
  return chooseBest(await searchMovies(title, year), title, year);
}

const runtimeText = (minutes: unknown) => {
  const m = Number(minutes) || 0;
  if (!m) return "";
  return m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m}m`;
};

const crewName = (credits: Raw, ...jobs: string[]) =>
  String((credits.crew ?? []).find((p: Raw) => jobs.includes(p.job) && p.name)?.name ?? "");

export async function getDetails(id: number): Promise<MovieDetails> {
  const data = await tmdb(`/movie/${id}`, { append_to_response: "credits" });
  const base = toMovie(data);
  if (!base) throw new HttpError(404, "Film not found on TMDB.");
  const credits: Raw = data.credits ?? {};
  return {
    ...base,
    poster: image(data.poster_path, "w500"),
    runtime: runtimeText(data.runtime),
    genres: (data.genres ?? []).map((g: Raw) => String(g.name)).filter(Boolean),
    director: crewName(credits, "Director"),
    cinematographer: crewName(credits, "Director of Photography"),
    composer: crewName(credits, "Original Music Composer", "Composer"),
    cast: (credits.cast ?? [])
      .slice(0, 6)
      .filter((p: Raw) => p.name)
      .map((p: Raw) => ({ name: String(p.name), character: String(p.character ?? "") })),
    tagline: String(data.tagline ?? ""),
    backdrop: image(data.backdrop_path, "w1280"),
  };
}

export async function getSimilar(id: number, limit = 6): Promise<Movie[]> {
  const data = await tmdb(`/movie/${id}/recommendations`);
  return toMovies(data.results).slice(0, limit);
}

const LISTS: Record<ListKind, string> = {
  popular: "/movie/popular",
  trending: "/trending/movie/week",
  top_rated: "/movie/top_rated",
  now_playing: "/movie/now_playing",
};

export function isListKind(value: string): value is ListKind {
  return value in LISTS;
}

export async function listMovies(kind: ListKind, page = 1): Promise<MovieListResponse> {
  const safePage = Math.min(Math.max(Math.floor(page) || 1, 1), 50);
  const data = await tmdb(LISTS[kind], { page: safePage, include_adult: "false" });
  return {
    items: toMovies(data.results),
    page: safePage,
    totalPages: Math.min(Number(data.total_pages) || 1, 50),
  };
}

export function facts(movie: MovieDetails): string {
  const rows: [string, string][] = [
    ["Title", movie.title],
    ["Year", movie.year],
    ["Runtime", movie.runtime],
    ["Genres", movie.genres.join(", ")],
    ["Director", movie.director],
    ["Cinematographer", movie.cinematographer],
    ["Composer", movie.composer],
    ["Cast", movie.cast.map((c) => (c.character ? `${c.name} as ${c.character}` : c.name)).join(", ")],
    ["Overview", movie.overview],
  ];
  return rows
    .filter(([, value]) => value)
    .map(([label, value]) => `- ${label}: ${value}`)
    .join("\n");
}
