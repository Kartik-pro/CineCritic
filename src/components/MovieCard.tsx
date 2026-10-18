import type { ReactNode } from "react";
import type { Movie } from "../../shared/types";
import { Poster } from "./Poster";

interface Props {
  movie: Movie;
  onOpen: (movie: Movie) => void;
  note?: string;
  children?: ReactNode;
}

export function MovieCard({ movie, onOpen, note, children }: Props) {
  return (
    <article className="card">
      <button className="card-main" onClick={() => onOpen(movie)} aria-label={`Analyze ${movie.title}`}>
        <Poster src={movie.poster} title={movie.title} />
        <span className="card-body">
          <strong className="card-title">{movie.title}</strong>
          <span className="muted">
            {movie.year || "—"}
            {movie.rating !== null && ` · ★ ${movie.rating.toFixed(1)}`}
          </span>
          {note && <span className="note">{note}</span>}
        </span>
      </button>
      {children}
    </article>
  );
}

export function MovieGrid({ children }: { children: ReactNode }) {
  return <div className="grid">{children}</div>;
}
