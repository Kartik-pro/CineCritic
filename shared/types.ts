export const SPOILER_LEVELS = ["none", "light", "full"] as const;
export type SpoilerLevel = (typeof SPOILER_LEVELS)[number];

export const SPOILER_LABELS: Record<SpoilerLevel, string> = {
  none: "Spoiler-free",
  light: "Light spoilers",
  full: "Full spoilers",
};

export const LANGUAGES = [
  "English",
  "Hindi",
  "Spanish",
  "French",
  "German",
  "Japanese",
  "Portuguese",
  "Italian",
] as const;

export const DIMENSIONS = [
  { key: "plot", title: "Plot & Premise", short: "Plot" },
  { key: "screenplay", title: "Story & Screenplay", short: "Screenplay" },
  { key: "direction", title: "Direction & Vision", short: "Direction" },
  { key: "acting", title: "Acting & Performances", short: "Acting" },
  { key: "cinematography", title: "Cinematography & Visuals", short: "Cinematography" },
  { key: "music", title: "Music & Sound Design", short: "Sound & Music" },
  { key: "pacing", title: "Editing & Pacing", short: "Editing" },
  { key: "themes", title: "Emotional Impact & Themes", short: "Themes" },
] as const;

export type DimensionKey = (typeof DIMENSIONS)[number]["key"];

export interface Movie {
  id: number;
  title: string;
  year: string;
  overview: string;
  poster: string;
  rating: number | null;
}

export interface MovieDetails extends Movie {
  runtime: string;
  genres: string[];
  director: string;
  cinematographer: string;
  composer: string;
  cast: { name: string; character: string }[];
  tagline: string;
  backdrop: string;
}

export interface Dimension {
  score: number | null;
  summary: string;
  detail: string;
}

export interface Critique {
  dimensions: Record<DimensionKey, Dimension>;
  overall: number | null;
  verdictLabel: string;
  verdictText: string;
  pullQuote: string;
  recommendation: string;
  quickTake: string[];
  strengths: string[];
  flaws: string[];
  tags: string[];
  spoilerNotes: string;
}

export interface Analysis {
  movie: MovieDetails;
  critique: Critique;
  similar: Movie[];
  spoiler: SpoilerLevel;
  language: string;
  notices: string[];
  createdAt: number;
}

export interface Pick extends Movie {
  why: string;
}

export interface CritiqueResponse {
  analysis: Analysis;
  alternatives: Movie[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export type ListKind = "popular" | "trending" | "top_rated" | "now_playing";

export interface MovieListResponse {
  items: Movie[];
  page: number;
  totalPages: number;
}
