import { useState } from "react";
import { DIMENSIONS, type Analysis, type Movie } from "../../shared/types";
import { compareScores, dimensionScores, type Comparison } from "../../shared/scoring";
import { RunPanel } from "../components/Pipeline";
import { operations } from "../pipeline/operations";
import { useRunner } from "../pipeline/useRunner";
import { Poster } from "../components/Poster";
import { SearchBox } from "../components/SearchBox";
import { ErrorNote } from "../components/Status";
import { useApp } from "../state";

interface Side {
  text: string;
  picked: Movie | null;
}

interface Result {
  a: Analysis;
  b: Analysis;
  comparison: Comparison;
  narrative: string;
}

const empty: Side = { text: "", picked: null };

function verdict(result: Result): string {
  const { a, b, comparison } = result;
  if (comparison.leader === "a") return `${a.movie.title} leads on CineCritic's scores.`;
  if (comparison.leader === "b") return `${b.movie.title} leads on CineCritic's scores.`;
  if (comparison.leader === "close") return "Too close to call — the scores are nearly level.";
  return "Not enough comparable scores to name a leader.";
}

export function Battle() {
  const { prefs, cachedAnalysis, remember } = useApp();
  const runner = useRunner();
  const [a, setA] = useState<Side>(empty);
  const [b, setB] = useState<Side>(empty);
  const [error, setError] = useState("");
  const loading = runner.busy;
  const [result, setResult] = useState<Result | null>(null);

  const target = (side: Side) => {
    const cached = side.picked ? cachedAnalysis(side.picked.id) : null;
    if (cached) return { analysis: cached };
    return side.picked ? { id: side.picked.id } : { query: side.text.trim() };
  };

  const fight = async () => {
    if (!a.text.trim() || !b.text.trim() || loading) return;
    if (a.text.trim().toLowerCase() === b.text.trim().toLowerCase()) {
      setError("Pick two different films to compare.");
      return;
    }
    setError("");
    setResult(null);
    const response = await runner.start(operations.battle(target(a), target(b), prefs));
    if (!response) return;
    remember([response.a, response.b]);
    setResult({
      a: response.a,
      b: response.b,
      comparison: compareScores(dimensionScores(response.a.critique), dimensionScores(response.b.critique)),
      narrative: response.narrative,
    });
  };

  return (
    <div>
      <h2 className="page-title">Head-to-head battle</h2>
      <p className="muted">Compare two films category by category. Scores are CineCritic's AI assessments, not a verdict on art.</p>
      <div className="versus">
        <SearchBox
          value={a.text}
          label="First film"
          placeholder="First film"
          onChange={(text, picked) => setA({ text, picked })}
          onSubmit={() => void fight()}
        />
        <span className="vs">VS</span>
        <SearchBox
          value={b.text}
          label="Second film"
          placeholder="Second film"
          onChange={(text, picked) => setB({ text, picked })}
          onSubmit={() => void fight()}
        />
      </div>
      <button className="primary" disabled={loading || !a.text.trim() || !b.text.trim()} onClick={() => void fight()}>
        Compare
      </button>
      <ErrorNote message={error} />
      <RunPanel run={runner.run} onCancel={runner.cancel} onRetry={() => void fight()} />

      {result && !loading && (
        <div className="analysis">
          <section className="panel versus-head">
            {[result.a, result.b].map((x, i) => (
              <div key={x.movie.id} className="contender">
                <Poster src={x.movie.poster} title={x.movie.title} className="mini" />
                <div>
                  <h3>{x.movie.title}</h3>
                  <p className="muted">{x.movie.year}</p>
                  <strong className="big">
                    {(i === 0 ? result.comparison.overallA : result.comparison.overallB)?.toFixed(1) ?? "—"}
                  </strong>
                </div>
              </div>
            ))}
          </section>
          <p className="notice strong">{verdict(result)}</p>
          <section className="panel">
            <table className="table">
              <thead>
                <tr>
                  <th>Category</th>
                  <th>{result.a.movie.title}</th>
                  <th>{result.b.movie.title}</th>
                </tr>
              </thead>
              <tbody>
                {result.comparison.rows.map((row) => (
                  <tr key={row.key}>
                    <th scope="row">{DIMENSIONS.find((d) => d.key === row.key)?.short}</th>
                    <td className={row.outcome === "a" ? "win" : ""}>{row.a?.toFixed(1) ?? "—"}</td>
                    <td className={row.outcome === "b" ? "win" : ""}>{row.b?.toFixed(1) ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted small">
              Compared on {result.comparison.comparable} of {DIMENSIONS.length} categories. Gaps under 0.3 count as ties; a film leads only if its average is at least 0.5 higher.
            </p>
          </section>
          {result.narrative && (
            <section className="panel prose">
              {result.narrative.split(/\n{2,}/).map((p) => (
                <p key={p}>{p}</p>
              ))}
            </section>
          )}
        </div>
      )}
    </div>
  );
}
