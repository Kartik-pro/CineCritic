import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react";
import type { Analysis, ChatMessage, Movie, SpoilerLevel } from "../shared/types";
import { api, setCredentials, type Availability, type Options, type Target } from "./api";
import { loadCredentials, saveCredentials, type Credentials } from "./keys";
import { operations } from "./pipeline/operations";
import type { Started } from "./pipeline/store";
import type { CritiqueResponse } from "../shared/types";

export type Page = "critique" | "discover" | "ask" | "battle" | "watchlist" | "monitor" | "account" | "settings";
export const PAGES: { id: Page; label: string }[] = [
  { id: "critique", label: "Critique" },
  { id: "discover", label: "Discover" },
  { id: "ask", label: "Ask" },
  { id: "battle", label: "Battle" },
  { id: "watchlist", label: "Watchlist" },
  { id: "monitor", label: "Monitor" },
  { id: "account", label: "Account" },
  { id: "settings", label: "Settings" },
];

export type Status = "planned" | "watching" | "watched";

export interface Entry {
  id: number;
  title: string;
  year: string;
  poster: string;
  status: Status;
  rating: number | null;
  favorite: boolean;
  review: string;
  updatedAt: number;
}

export type Prefs = Options;

const HISTORY_LIMIT = 20;
const CACHE_MS = 7 * 24 * 60 * 60 * 1000;

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function useStored<T>(key: string, initial: T): [T, Dispatch<SetStateAction<T>>] {
  const [value, setValue] = useState<T>(() => read(key, initial));
  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      return;
    }
  }, [key, value]);
  return [value, setValue];
}

function pageFromHash(): Page {
  const id = window.location.hash.replace(/^#\/?/, "");
  return PAGES.find((p) => p.id === id)?.id ?? "critique";
}

interface AppState {
  page: Page;
  go: (page: Page) => void;
  prefs: Prefs;
  setPrefs: (prefs: Prefs) => void;
  creds: Credentials;
  setCreds: (creds: Credentials) => void;
  available: Availability | null;
  current: Analysis | null;
  setCurrent: (analysis: Analysis | null) => void;
  history: Analysis[];
  pending: Target | null;
  analyze: (target: Target) => void;
  clearPending: () => void;
  runAnalysis: (target: Target) => { id: string | null; promise: Promise<CritiqueResponse> };
  cachedAnalysis: (id: number) => Analysis | null;
  remember: (analyses: Analysis[]) => void;
  watchlist: Record<number, Entry>;
  saveEntry: (movie: Pick<Movie, "id" | "title" | "year" | "poster">, patch: Partial<Entry>) => void;
  removeEntry: (id: number) => void;
  importEntries: (entries: Entry[]) => number;
  chat: ChatMessage[];
  setChat: Dispatch<SetStateAction<ChatMessage[]>>;
}

const Context = createContext<AppState | null>(null);

export function useApp(): AppState {
  const value = useContext(Context);
  if (!value) throw new Error("useApp must be used inside AppProvider");
  return value;
}

const STATUSES: Status[] = ["planned", "watching", "watched"];

export function parseEntries(value: unknown): Entry[] {
  const items = Array.isArray(value) ? value : [];
  return items.flatMap((item): Entry[] => {
    if (!item || typeof item !== "object") return [];
    const e = item as Record<string, unknown>;
    if (typeof e.id !== "number" || typeof e.title !== "string") return [];
    const rating = typeof e.rating === "number" && e.rating >= 0 && e.rating <= 10 ? e.rating : null;
    return [
      {
        id: e.id,
        title: e.title.slice(0, 200),
        year: typeof e.year === "string" ? e.year.slice(0, 4) : "",
        poster: typeof e.poster === "string" && e.poster.startsWith("https://image.tmdb.org/") ? e.poster : "",
        status: STATUSES.includes(e.status as Status) ? (e.status as Status) : "planned",
        rating,
        favorite: e.favorite === true,
        review: typeof e.review === "string" ? e.review.slice(0, 4000) : "",
        updatedAt: typeof e.updatedAt === "number" ? e.updatedAt : Date.now(),
      },
    ];
  });
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [page, setPage] = useState<Page>(pageFromHash);
  const [prefs, setPrefs] = useStored<Prefs>("cc.prefs", { spoiler: "none" as SpoilerLevel, language: "English" });
  const [creds, setCredsState] = useState<Credentials>(() => {
    const loaded = loadCredentials();
    setCredentials(loaded);
    return loaded;
  });
  const setCreds = useCallback((next: Credentials) => {
    saveCredentials(next);
    setCredentials(next);
    setCredsState(next);
  }, []);
  const [available, setAvailable] = useState<Availability | null>(null);
  const [history, setHistory] = useStored<Analysis[]>("cc.history", []);
  const [watchlist, setWatchlist] = useStored<Record<number, Entry>>("cc.watchlist", {});
  const [current, setCurrent] = useState<Analysis | null>(null);
  const [pending, setPending] = useState<Target | null>(null);
  const [chat, setChat] = useState<ChatMessage[]>([]);

  useEffect(() => {
    let live = true;
    api
      .status()
      .then((result) => live && setAvailable(result))
      .catch(() => live && setAvailable(null));
    return () => {
      live = false;
    };
  }, [creds]);

  useEffect(() => {
    const onHash = () => setPage(pageFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const go = useCallback((next: Page) => {
    window.location.hash = `/${next}`;
    setPage(next);
    window.scrollTo({ top: 0 });
  }, []);

  const analyze = useCallback(
    (target: Target) => {
      setPending(target);
      go("critique");
    },
    [go],
  );

  const clearPending = useCallback(() => setPending(null), []);

  const remember = useCallback(
    (analyses: Analysis[]) =>
      setHistory((prev) => {
        const incoming = new Set(analyses.map((a) => a.movie.id));
        return [...analyses, ...prev.filter((a) => !incoming.has(a.movie.id))].slice(0, HISTORY_LIMIT);
      }),
    [setHistory],
  );

  const cachedAnalysis = useCallback(
    (id: number) =>
      history.find(
        (a) => a.movie.id === id && a.spoiler === prefs.spoiler && a.language === prefs.language && Date.now() - a.createdAt < CACHE_MS,
      ) ?? null,
    [history, prefs],
  );

  const runAnalysis = useCallback(
    (target: Target) => {
      const hit = target.id ? cachedAnalysis(target.id) : null;
      if (hit) return { id: null, promise: Promise.resolve<CritiqueResponse>({ analysis: hit, alternatives: [] }) };
      const started: Started<CritiqueResponse> = operations.critique(target, prefs);
      const promise = started.promise.then((response) => {
        remember([response.analysis]);
        return response;
      });
      return { id: started.id, promise };
    },
    [cachedAnalysis, prefs, remember],
  );

  const saveEntry = useCallback<AppState["saveEntry"]>(
    (movie, patch) => {
      setWatchlist((prev) => {
        const existing = prev[movie.id];
        const base: Entry = existing ?? {
          id: movie.id,
          title: movie.title,
          year: movie.year,
          poster: movie.poster,
          status: "planned",
          rating: null,
          favorite: false,
          review: "",
          updatedAt: 0,
        };
        return { ...prev, [movie.id]: { ...base, ...patch, updatedAt: Date.now() } };
      });
    },
    [setWatchlist],
  );

  const removeEntry = useCallback(
    (id: number) =>
      setWatchlist((prev) => {
        const { [id]: _removed, ...rest } = prev;
        return rest;
      }),
    [setWatchlist],
  );

  const importEntries = useCallback(
    (entries: Entry[]) => {
      setWatchlist((prev) => ({ ...prev, ...Object.fromEntries(entries.map((e) => [e.id, e])) }));
      return entries.length;
    },
    [setWatchlist],
  );

  const value = useMemo<AppState>(
    () => ({
      page, go, prefs, setPrefs, creds, setCreds, available, current, setCurrent, history, pending, analyze, clearPending,
      runAnalysis, cachedAnalysis, remember, watchlist, saveEntry, removeEntry, importEntries, chat, setChat,
    }),
    [page, go, prefs, setPrefs, creds, setCreds, available, current, history, pending, analyze, clearPending, runAnalysis, cachedAnalysis, remember, watchlist, saveEntry, removeEntry, importEntries, chat],
  );

  return <Context.Provider value={value}>{children}</Context.Provider>;
}
