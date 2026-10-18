import { SpeedInsights } from "@vercel/speed-insights/react";
import { LANGUAGES, SPOILER_LABELS, SPOILER_LEVELS, type SpoilerLevel } from "../shared/types";
import { Ask } from "./pages/Ask";
import { Battle } from "./pages/Battle";
import { Critique } from "./pages/Critique";
import { Discover } from "./pages/Discover";
import { Settings } from "./pages/Settings";
import { Watchlist } from "./pages/Watchlist";
import { AppProvider, PAGES, useApp } from "./state";

function Shell() {
  const { page, go, prefs, setPrefs, watchlist, available } = useApp();
  const needsKeys = available !== null && (!available.tmdb || !available.ai);
  const saved = Object.keys(watchlist).length;

  return (
    <>
      <header className="top">
        <button className="brand" onClick={() => go("critique")} aria-label="CineCritic home">
          CINE<span>CRITIC</span>
        </button>
        <nav aria-label="Main">
          {PAGES.map((p) => (
            <button key={p.id} className={page === p.id ? "nav on" : "nav"} aria-current={page === p.id ? "page" : undefined} onClick={() => go(p.id)}>
              {p.label}
              {p.id === "watchlist" && saved > 0 && <span className="count">{saved}</span>}
            </button>
          ))}
        </nav>
        <div className="prefs">
          <select
            aria-label="Spoiler protection"
            value={prefs.spoiler}
            onChange={(e) => setPrefs({ ...prefs, spoiler: e.target.value as SpoilerLevel })}
          >
            {SPOILER_LEVELS.map((level) => (
              <option key={level} value={level}>
                {SPOILER_LABELS[level]}
              </option>
            ))}
          </select>
          <select aria-label="Language" value={prefs.language} onChange={(e) => setPrefs({ ...prefs, language: e.target.value })}>
            {LANGUAGES.map((l) => (
              <option key={l}>{l}</option>
            ))}
          </select>
        </div>
      </header>
      {needsKeys && page !== "settings" && (
        <p className="banner" role="status">
          Add your TMDB and AI API keys to get started.{" "}
          <button className="link" onClick={() => go("settings")}>
            Open Settings
          </button>
        </p>
      )}
      <main>
        {page === "settings" && <Settings />}
        {page === "critique" && <Critique />}
        {page === "discover" && <Discover />}
        {page === "ask" && <Ask />}
        {page === "battle" && <Battle />}
        {page === "watchlist" && <Watchlist />}
      </main>
      <footer>
        Film data by TMDB. This product uses the TMDB API but is not endorsed or certified by TMDB. AI scores are subjective assessments, not IMDb or audience ratings.
      </footer>
    </>
  );
}

export default function App() {
  return (
    <AppProvider>
      <Shell />
      <SpeedInsights />
    </AppProvider>
  );
}