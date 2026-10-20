import { useCallback, useEffect, useState } from "react";
import type { ListKind, Movie, Pick } from "../../shared/types";
import { api } from "../api";
import { RunPanel } from "../components/Pipeline";
import { operations } from "../pipeline/operations";
import { useRunner } from "../pipeline/useRunner";
import { MovieCard, MovieGrid } from "../components/MovieCard";
import { ErrorNote, Loading } from "../components/Status";
import { useApp } from "../state";

type Tab = ListKind | "ai";

const TABS: { id: Tab; label: string }[] = [
  { id: "popular", label: "Popular" },
  { id: "trending", label: "Trending" },
  { id: "top_rated", label: "Top rated" },
  { id: "now_playing", label: "In cinemas" },
  { id: "ai", label: "Describe a mood" },
];

function Browse({ kind }: { kind: ListKind }) {
  const { analyze } = useApp();
  const [items, setItems] = useState<Movie[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(
    async (next: number) => {
      setLoading(true);
      setError("");
      try {
        const data = await api.list(kind, next);
        setItems((prev) => (next === 1 ? data.items : [...prev, ...data.items.filter((m) => !prev.some((p) => p.id === m.id))]));
        setPage(data.page);
        setTotalPages(data.totalPages);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not load films.");
      } finally {
        setLoading(false);
      }
    },
    [kind],
  );

  useEffect(() => {
    setItems([]);
    void load(1);
  }, [load]);

  return (
    <>
      <ErrorNote message={error} />
      <MovieGrid>
        {items.map((m) => (
          <MovieCard key={m.id} movie={m} onOpen={(movie) => analyze({ id: movie.id })} />
        ))}
      </MovieGrid>
      {loading && <Loading text="Loading from TMDB…" />}
      {!loading && page < totalPages && (
        <button className="ghost center" onClick={() => void load(page + 1)}>
          Load more
        </button>
      )}
    </>
  );
}

function Describe() {
  const { analyze } = useApp();
  const [text, setText] = useState("");
  const [picks, setPicks] = useState<Pick[]>([]);
  const runner = useRunner();

  const find = async (input = text) => {
    const value = input.trim();
    if (!value || runner.busy) return;
    setPicks([]);
    const result = await runner.start(operations.discover(value));
    if (result) setPicks(result.picks);
  };

  return (
    <>
      <p className="muted">Describe a film you love, a mood, or a plot you half-remember. Every pick is verified on TMDB.</p>
      <div className="stack">
        <textarea
          rows={3}
          maxLength={300}
          value={text}
          placeholder="Slow-burn sci-fi with big ideas, like Arrival and Ex Machina"
          aria-label="Describe what you want to watch"
          onChange={(e) => setText(e.target.value)}
        />
        <button className="primary" disabled={runner.busy || !text.trim()} onClick={() => void find()}>
          Find films
        </button>
      </div>
      <RunPanel run={runner.run} onCancel={runner.cancel} onRetry={() => void find(runner.run?.retry?.text ?? text)} />
      <MovieGrid>
        {picks.map((m) => (
          <MovieCard key={m.id} movie={m} note={m.why} onOpen={(movie) => analyze({ id: movie.id })} />
        ))}
      </MovieGrid>
    </>
  );
}

export function Discover() {
  const [tab, setTab] = useState<Tab>("popular");
  return (
    <div>
      <h2 className="page-title">Discover</h2>
      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? "tab on" : "tab"} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === "ai" ? <Describe /> : <Browse key={tab} kind={tab} />}
    </div>
  );
}
