import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { Movie } from "../../shared/types";
import { api } from "../api";
import { Poster } from "./Poster";

interface Props {
  value: string;
  placeholder: string;
  label: string;
  onChange: (text: string, picked: Movie | null) => void;
  onSubmit?: () => void;
}

export function SearchBox({ value, placeholder, label, onChange, onSubmit }: Props) {
  const [items, setItems] = useState<Movie[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const skip = useRef(false);

  useEffect(() => {
    if (skip.current) {
      skip.current = false;
      return;
    }
    if (value.trim().length < 3) {
      setItems([]);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api
        .search(value.trim(), controller.signal)
        .then((data) => {
          setItems(data.items.slice(0, 6));
          setOpen(true);
          setActive(-1);
        })
        .catch(() => setItems([]));
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [value]);

  const pick = (movie: Movie) => {
    skip.current = true;
    onChange(movie.year ? `${movie.title} (${movie.year})` : movie.title, movie);
    setItems([]);
    setOpen(false);
  };

  const onKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" && items.length) {
      event.preventDefault();
      setActive((i) => (i + 1) % items.length);
    } else if (event.key === "ArrowUp" && items.length) {
      event.preventDefault();
      setActive((i) => (i <= 0 ? items.length - 1 : i - 1));
    } else if (event.key === "Escape") {
      setOpen(false);
    } else if (event.key === "Enter") {
      event.preventDefault();
      const chosen = open ? items[active] : undefined;
      if (chosen) pick(chosen);
      else {
        setOpen(false);
        onSubmit?.();
      }
    }
  };

  return (
    <div className="search">
      <input
        type="text"
        value={value}
        maxLength={120}
        placeholder={placeholder}
        aria-label={label}
        role="combobox"
        aria-expanded={open && items.length > 0}
        aria-autocomplete="list"
        autoComplete="off"
        onChange={(e) => onChange(e.target.value, null)}
        onKeyDown={onKey}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open && items.length > 0 && (
        <ul className="suggest" role="listbox">
          {items.map((movie, index) => (
            <li key={movie.id} role="option" aria-selected={index === active}>
              <button className={index === active ? "active" : ""} onMouseDown={() => pick(movie)} tabIndex={-1}>
                <Poster src={movie.poster} title={movie.title} className="thumb" />
                <span>
                  {movie.title} <span className="muted">{movie.year}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
