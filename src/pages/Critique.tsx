import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import type { Movie } from "../../shared/types";
import type { Target } from "../api";
import { AnalysisView } from "../components/AnalysisView";
import { SearchBox } from "../components/SearchBox";
import { RunPanel } from "../components/Pipeline";
import { ErrorNote } from "../components/Status";
import { useRunner } from "../pipeline/useRunner";
import { useApp } from "../state";

const EXAMPLES = ["Oppenheimer (2023)", "Dune: Part Two", "Interstellar", "Parasite", "Past Lives"];

export function Critique() {
  const { prefs, current, setCurrent, pending, clearPending, runAnalysis } = useApp();
  const runner = useRunner();
  const [text, setText] = useState("");
  const [picked, setPicked] = useState<Movie | null>(null);
  const [alternatives, setAlternatives] = useState<Movie[]>([]);
  const [error, setError] = useState("");
  const latest = useRef(0);
  const loading = runner.busy;

  const run = useCallback(
    async (target: Target) => {
      const ticket = ++latest.current;
      setError("");
      const { id, promise } = runAnalysis(target);
      if (id === null) runner.reset();
      const result = await (id === null ? promise.catch(() => undefined) : runner.start({ id, promise }));
      if (ticket !== latest.current || !result) return;
      setCurrent(result.analysis);
      setAlternatives(result.alternatives);
      setText(result.analysis.movie.year ? `${result.analysis.movie.title} (${result.analysis.movie.year})` : result.analysis.movie.title);
    },
    [runAnalysis, runner.start, runner.reset, setCurrent],
  );

  useEffect(() => {
    if (!pending) return;
    clearPending();
    void run(pending);
  }, [pending, clearPending, run]);

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    const query = text.trim();
    if (!query || loading) return;
    void run(picked ? { id: picked.id } : { query });
  };

  const stale = current && (current.spoiler !== prefs.spoiler || current.language !== prefs.language);

  return (
    <div>
      <section className="hero">
        <p className="eyebrow">AI cinema intelligence</p>
        <h1>
          Know the film <em>before</em> you press play.
        </h1>
        <p className="lede">Spoiler-safe critiques with eight craft scorecards, grounded in verified TMDB credits.</p>
        <form className="search-form" onSubmit={submit}>
          <SearchBox
            value={text}
            label="Film title"
            placeholder="Search a film — e.g. Oppenheimer (2023)"
            onChange={(value, movie) => {
              setText(value);
              setPicked(movie);
            }}
            onSubmit={submit}
          />
          <button className="primary" type="submit" disabled={loading || !text.trim()}>
            Analyze
          </button>
        </form>
        <div className="chips">
          {EXAMPLES.map((title) => (
            <button key={title} className="chip" disabled={loading} onClick={() => void run({ query: title })}>
              {title}
            </button>
          ))}
        </div>
      </section>

      <ErrorNote message={error} />
      <RunPanel run={runner.run} onCancel={runner.cancel} onRetry={() => runner.run?.retry?.target && void run(runner.run.retry.target)} />

      {!loading && current && (
        <>
          {alternatives.length > 0 && (
            <p className="alternatives">
              Not this one?{" "}
              {alternatives.map((m) => (
                <button key={m.id} className="link" onClick={() => void run({ id: m.id })}>
                  {m.title} ({m.year})
                </button>
              ))}
            </p>
          )}
          {stale && (
            <p className="notice">
              Your spoiler or language setting changed.{" "}
              <button className="link" onClick={() => void run({ id: current.movie.id })}>
                Re-run with the new settings
              </button>
            </p>
          )}
          <AnalysisView key={`${current.movie.id}-${current.createdAt}`} analysis={current} onAnalyze={(t) => void run(t)} />
        </>
      )}
    </div>
  );
}
