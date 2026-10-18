import { useState, type FormEvent } from "react";
import { AI_PROVIDERS, EMPTY_KEYS, type AiProvider, type StoredKeys } from "../api";
import { useApp } from "../state";

const clean = (value: string) => value.replace(/[^\x21-\x7e]/g, "");

export function Settings() {
  const { keys, setKeys, available, go } = useApp();
  const [draft, setDraft] = useState<StoredKeys>(keys);
  const [visible, setVisible] = useState(false);
  const [saved, setSaved] = useState(false);
  const provider = AI_PROVIDERS.find((p) => p.id === draft.provider) ?? AI_PROVIDERS[0];
  const type = visible ? "text" : "password";

  const edit = (patch: Partial<StoredKeys>) => {
    setDraft((prev) => ({ ...prev, ...patch }));
    setSaved(false);
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const next = { ...draft, tmdb: clean(draft.tmdb), ai: clean(draft.ai), model: clean(draft.model) };
    setDraft(next);
    setKeys(next);
    setSaved(true);
  };

  const clear = () => {
    setDraft(EMPTY_KEYS);
    setKeys(EMPTY_KEYS);
    setSaved(false);
  };

  const ready = !!available?.tmdb && !!available.ai;

  return (
    <form className="panel settings" onSubmit={submit}>
      <div>
        <p className="eyebrow">Settings</p>
        <h2>API keys</h2>
        <p className="muted">
          Paste your own keys to use CineCritic. They are saved only in this browser and sent securely with each request. They are never stored on the server.
        </p>
      </div>

      <label>
        TMDB API key
        <input type={type} value={draft.tmdb} onChange={(e) => edit({ tmdb: e.target.value })} placeholder="TMDB v3 key or v4 read token" autoComplete="off" spellCheck={false} />
        <a href="https://www.themoviedb.org/settings/api" target="_blank" rel="noopener noreferrer">
          Get a free TMDB key
        </a>
      </label>

      <label>
        AI provider
        <select value={draft.provider} onChange={(e) => edit({ provider: e.target.value as AiProvider })}>
          {AI_PROVIDERS.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
      </label>

      <label>
        {provider.label} API key
        <input type={type} value={draft.ai} onChange={(e) => edit({ ai: e.target.value })} placeholder="Paste your key" autoComplete="off" spellCheck={false} />
      </label>

      <label>
        Model (optional)
        <input type="text" value={draft.model} onChange={(e) => edit({ model: e.target.value })} placeholder={provider.model} autoComplete="off" spellCheck={false} />
      </label>

      <label className="check">
        <input type="checkbox" checked={visible} onChange={(e) => setVisible(e.target.checked)} />
        Show keys
      </label>

      {saved && (
        <p className="notice">
          {ready ? "Saved. You're ready to analyze films." : "Saved. Add both a TMDB key and an AI key to continue."}
        </p>
      )}

      <div className="row">
        <button className="primary" type="submit">
          Save keys
        </button>
        {saved && ready && (
          <button className="ghost" type="button" onClick={() => go("critique")}>
            Start analyzing
          </button>
        )}
        <button className="ghost danger" type="button" onClick={clear}>
          Clear keys
        </button>
      </div>
    </form>
  );
}
