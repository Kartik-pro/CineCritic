import { useState } from "react";
import { DIMENSIONS, SPOILER_LABELS, type Analysis } from "../../shared/types";
import { band, dimensionScores, overallScore } from "../../shared/scoring";
import type { Target } from "../api";
import { useApp, type Status } from "../state";
import { MovieCard, MovieGrid } from "./MovieCard";
import { Poster } from "./Poster";

const STATUS_OPTIONS: Status[] = ["planned", "watching", "watched"];

const scoreText = (score: number | null) => (score === null ? "—" : score.toFixed(1));

function download(analysis: Analysis) {
  const { spoilerNotes: _hidden, ...critique } = analysis.critique;
  const blob = new Blob([JSON.stringify({ ...analysis, critique }, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `cinecritic-${analysis.movie.title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

interface Props {
  analysis: Analysis;
  onAnalyze: (target: Target) => void;
}

export function AnalysisView({ analysis, onAnalyze }: Props) {
  const { movie, critique } = analysis;
  const { watchlist, saveEntry, go } = useApp();
  const saved = watchlist[movie.id];
  const [status, setStatus] = useState<Status>(saved?.status ?? "planned");
  const [rating, setRating] = useState(saved?.rating?.toString() ?? "");
  const [revealed, setRevealed] = useState(false);
  const scores = dimensionScores(critique);
  const overall = overallScore(critique);
  const meta = [movie.year, movie.runtime, movie.genres.join(", ")].filter(Boolean).join(" · ");
  const crew = [
    ["Director", movie.director],
    ["Cinematography", movie.cinematographer],
    ["Music", movie.composer],
  ].filter(([, name]) => name);

  const save = () => {
    const value = rating.trim() === "" ? null : Math.min(10, Math.max(0, Number(rating)));
    saveEntry(movie, { status, rating: Number.isFinite(value) ? value : null });
  };

  return (
    <div className="analysis">
      <section className="hero-film" style={movie.backdrop ? { backgroundImage: `url(${movie.backdrop})` } : undefined}>
        <div className="hero-shade">
          <Poster src={movie.poster} title={movie.title} className="hero-poster" />
          <div>
            <h2>{movie.title}</h2>
            <p className="muted">{meta}</p>
            {movie.tagline && <p className="tagline">“{movie.tagline}”</p>}
            <dl className="crew">
              {crew.map(([label, name]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{name}</dd>
                </div>
              ))}
              {movie.cast.length > 0 && (
                <div>
                  <dt>Cast</dt>
                  <dd>{movie.cast.map((c) => c.name).join(", ")}</dd>
                </div>
              )}
              {movie.rating !== null && (
                <div>
                  <dt>TMDB audience</dt>
                  <dd>★ {movie.rating.toFixed(1)}</dd>
                </div>
              )}
            </dl>
          </div>
        </div>
      </section>

      {analysis.notices.map((n) => (
        <p className="notice" key={n}>
          {n}
        </p>
      ))}

      <section className="panel verdict">
        <div className="score-ring" aria-label={`Overall score ${scoreText(overall)} out of 10`}>
          <strong>{scoreText(overall)}</strong>
          <span>{band(overall)}</span>
        </div>
        <div>
          <p className="eyebrow">CineCritic verdict · {SPOILER_LABELS[analysis.spoiler]}</p>
          <h3>{critique.verdictLabel || "Verdict"}</h3>
          {critique.pullQuote && <blockquote>{critique.pullQuote}</blockquote>}
          <p>{critique.verdictText}</p>
          {critique.recommendation && <p className="recommend">{critique.recommendation}</p>}
          {critique.tags.length > 0 && (
            <ul className="tags">
              {critique.tags.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {critique.quickTake.length > 0 && (
        <section className="panel">
          <h3>Quick take</h3>
          <ul className="bullets">
            {critique.quickTake.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </section>
      )}

      <section aria-label="Scorecards" className="scorecards">
        {DIMENSIONS.map(({ key, title }) => {
          const score = scores[key];
          const dimension = critique.dimensions[key];
          return (
            <article className="panel score" key={key}>
              <header>
                <h4>{title}</h4>
                <strong>{scoreText(score)}</strong>
              </header>
              <div className="bar" aria-hidden="true">
                <span style={{ width: `${(score ?? 0) * 10}%` }} />
              </div>
              <p>{dimension.summary}</p>
              <p className="muted">{dimension.detail}</p>
            </article>
          );
        })}
      </section>

      <section className="two">
        <div className="panel good">
          <h3>Strengths</h3>
          <ul className="bullets">
            {critique.strengths.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </div>
        <div className="panel bad">
          <h3>Weaknesses</h3>
          <ul className="bullets">
            {critique.flaws.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </div>
      </section>

      {critique.spoilerNotes && (
        <section className="panel spoiler">
          <h3>Spoiler notes</h3>
          {revealed ? (
            <p>{critique.spoilerNotes}</p>
          ) : (
            <button className="ghost" onClick={() => setRevealed(true)}>
              Reveal spoilers
            </button>
          )}
        </section>
      )}

      <section className="panel actions">
        <h3>Your watchlist</h3>
        <div className="row">
          <label>
            Status
            <select value={status} onChange={(e) => setStatus(e.target.value as Status)}>
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s[0]!.toUpperCase() + s.slice(1)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Your rating (0–10)
            <input type="number" min={0} max={10} step={0.5} value={rating} onChange={(e) => setRating(e.target.value)} />
          </label>
          <button className="primary" onClick={save}>
            {saved ? "Update" : "Save"}
          </button>
          <button className="ghost" onClick={() => go("ask")}>
            Ask the Critic
          </button>
          <button className="ghost" onClick={() => download(analysis)}>
            Download JSON
          </button>
        </div>
      </section>

      {analysis.similar.length > 0 && (
        <section>
          <h3 className="section-title">Similar films</h3>
          <MovieGrid>
            {analysis.similar.map((m) => (
              <MovieCard key={m.id} movie={m} onOpen={(picked) => onAnalyze({ id: picked.id })} />
            ))}
          </MovieGrid>
        </section>
      )}
    </div>
  );
}
