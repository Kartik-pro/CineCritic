import { useMemo, useRef, useState, type ChangeEvent } from "react";
import { parseEntries, useApp, type Entry, type Status } from "../state";
import { ErrorNote } from "../components/Status";
import { Poster } from "../components/Poster";

type Filter = "all" | Status | "favorites";
type Sort = "recent" | "title" | "rating";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "planned", label: "Planned" },
  { id: "watching", label: "Watching" },
  { id: "watched", label: "Watched" },
  { id: "favorites", label: "Favourites" },
];

const cell = (value: string) => {
  const safe = /^[=+\-@\t\r]/.test(value) ? `'${value}` : value;
  return `"${safe.replace(/"/g, '""')}"`;
};

function save(name: string, type: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

function Row({ entry }: { entry: Entry }) {
  const { saveEntry, removeEntry, analyze } = useApp();
  const [review, setReview] = useState(entry.review);
  const update = (patch: Partial<Entry>) => saveEntry(entry, patch);

  return (
    <article className="panel entry">
      <Poster src={entry.poster} title={entry.title} className="mini" />
      <div className="entry-body">
        <header>
          <h3>
            {entry.title} <span className="muted">{entry.year}</span>
          </h3>
          <button
            className={entry.favorite ? "fav on" : "fav"}
            aria-pressed={entry.favorite}
            aria-label={entry.favorite ? "Remove from favourites" : "Add to favourites"}
            onClick={() => update({ favorite: !entry.favorite })}
          >
            ★
          </button>
        </header>
        <div className="row">
          <label>
            Status
            <select value={entry.status} onChange={(e) => update({ status: e.target.value as Status })}>
              <option value="planned">Planned</option>
              <option value="watching">Watching</option>
              <option value="watched">Watched</option>
            </select>
          </label>
          <label>
            Rating (0–10)
            <input
              type="number"
              min={0}
              max={10}
              step={0.5}
              value={entry.rating ?? ""}
              onChange={(e) => update({ rating: e.target.value === "" ? null : Math.min(10, Math.max(0, Number(e.target.value))) })}
            />
          </label>
        </div>
        <textarea
          rows={2}
          maxLength={4000}
          value={review}
          placeholder="Your review or notes"
          aria-label={`Review of ${entry.title}`}
          onChange={(e) => setReview(e.target.value)}
          onBlur={() => review !== entry.review && update({ review })}
        />
        <div className="row">
          <button className="ghost" onClick={() => analyze({ id: entry.id })}>
            Analyze
          </button>
          <button className="ghost danger" onClick={() => window.confirm(`Remove “${entry.title}” from your watchlist?`) && removeEntry(entry.id)}>
            Remove
          </button>
        </div>
      </div>
    </article>
  );
}

export function Watchlist() {
  const { watchlist, importEntries } = useApp();
  const [filter, setFilter] = useState<Filter>("all");
  const [sort, setSort] = useState<Sort>("recent");
  const [query, setQuery] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const file = useRef<HTMLInputElement>(null);

  const all = useMemo(() => Object.values(watchlist), [watchlist]);
  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = all.filter(
      (e) =>
        (filter === "all" || (filter === "favorites" ? e.favorite : e.status === filter)) &&
        (!q || e.title.toLowerCase().includes(q) || e.review.toLowerCase().includes(q)),
    );
    return filtered.sort((x, y) =>
      sort === "title" ? x.title.localeCompare(y.title) : sort === "rating" ? (y.rating ?? -1) - (x.rating ?? -1) : y.updatedAt - x.updatedAt,
    );
  }, [all, filter, sort, query]);

  const rated = all.filter((e) => e.status === "watched" && e.rating !== null);
  const average = rated.length ? (rated.reduce((sum, e) => sum + (e.rating ?? 0), 0) / rated.length).toFixed(1) : "—";

  const exportCsv = () =>
    save(
      "cinecritic-watchlist.csv",
      "text/csv",
      [["Title", "Year", "Status", "Rating", "Favourite", "Review"], ...all.map((e) => [e.title, e.year, e.status, e.rating?.toString() ?? "", e.favorite ? "yes" : "", e.review])]
        .map((r) => r.map(cell).join(","))
        .join("\n"),
    );

  const onImport = async (event: ChangeEvent<HTMLInputElement>) => {
    const chosen = event.target.files?.[0];
    event.target.value = "";
    if (!chosen) return;
    setMessage("");
    setError("");
    let entries: Entry[] = [];
    try {
      if (chosen.size > 5_000_000) throw new Error("too large");
      entries = parseEntries(JSON.parse(await chosen.text()));
    } catch {
      setError("That file is not a valid CineCritic export.");
      return;
    }
    if (!entries.length) {
      setError("No films found in that file.");
      return;
    }
    setMessage(`Imported ${importEntries(entries)} film(s).`);
  };

  return (
    <div>
      <h2 className="page-title">Watchlist</h2>
      <p className="muted">Saved in this browser only. Export a backup to keep it or move it to another device.</p>
      <div className="stats">
        <div><strong>{all.length}</strong><span>Saved</span></div>
        <div><strong>{all.filter((e) => e.status === "watched").length}</strong><span>Watched</span></div>
        <div><strong>{average}</strong><span>Avg rating</span></div>
        <div><strong>{all.filter((e) => e.favorite).length}</strong><span>Favourites</span></div>
      </div>

      <div className="row toolbar">
        <input type="search" value={query} placeholder="Search title or review" aria-label="Search watchlist" onChange={(e) => setQuery(e.target.value)} />
        <select value={filter} aria-label="Filter" onChange={(e) => setFilter(e.target.value as Filter)}>
          {FILTERS.map((f) => (
            <option key={f.id} value={f.id}>{f.label}</option>
          ))}
        </select>
        <select value={sort} aria-label="Sort" onChange={(e) => setSort(e.target.value as Sort)}>
          <option value="recent">Recently updated</option>
          <option value="title">Title</option>
          <option value="rating">Rating</option>
        </select>
      </div>

      {rows.length === 0 ? (
        <p className="empty">{all.length ? "Nothing matches your filters." : "Nothing here yet. Analyze a film and save it to start your watchlist."}</p>
      ) : (
        rows.map((entry) => <Row key={entry.id} entry={entry} />)
      )}

      <div className="row">
        <button className="ghost" disabled={!all.length} onClick={() => save("cinecritic-watchlist.json", "application/json", JSON.stringify(all, null, 2))}>
          Export JSON
        </button>
        <button className="ghost" disabled={!all.length} onClick={exportCsv}>
          Export CSV
        </button>
        <button className="ghost" onClick={() => file.current?.click()}>
          Import JSON
        </button>
        <input ref={file} type="file" accept="application/json" hidden onChange={(e) => void onImport(e)} />
      </div>
      {message && <p className="notice">{message}</p>}
      <ErrorNote message={error} />
    </div>
  );
}
