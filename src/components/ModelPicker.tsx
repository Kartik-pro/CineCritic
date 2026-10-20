import { useEffect, useId, useMemo, useState } from "react";
import { MODEL_ID_PATTERN, PROVIDERS, type ModelCatalogue, type ModelInfo } from "../../shared/providers";
import { api } from "../api";
import type { Credentials } from "../keys";

const SHOWN = 80;

const formatCount = (n: number): string => (n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M` : n >= 1000 ? `${Math.round(n / 1000)}K` : String(n));

function Badge({ model }: { model: ModelInfo }) {
  if (model.compatible === false) return <span className="badge bad">Not compatible</span>;
  if (model.recommended) return <span className="badge good">Recommended</span>;
  if (model.compatible === null) return <span className="badge">Unverified</span>;
  return null;
}

function Details({ model, custom }: { model: ModelInfo | null; custom: string }) {
  if (!model) {
    return (
      <div className="model-details">
        <p className="muted">
          <strong>{custom}</strong> is not in the loaded list. It will be sent to the provider exactly as typed. Use Test connection to verify it works.
        </p>
      </div>
    );
  }
  return (
    <div className="model-details">
      <h4>{model.name}</h4>
      <p className="muted small">
        <code>{model.id}</code>
      </p>
      {model.description && <p>{model.description}</p>}
      <dl className="facts">
        {model.contextLength !== undefined && (
          <div>
            <dt>Context window</dt>
            <dd>{formatCount(model.contextLength)} tokens</dd>
          </div>
        )}
        {model.maxOutput !== undefined && (
          <div>
            <dt>Max output</dt>
            <dd>{formatCount(model.maxOutput)} tokens</dd>
          </div>
        )}
        {model.tasks.length > 0 && (
          <div>
            <dt>Reported tasks</dt>
            <dd>{model.tasks.join(", ")}</dd>
          </div>
        )}
        <div>
          <dt>Compatibility</dt>
          <dd>{model.compatible === true ? "Reported as compatible" : model.compatible === false ? "Reported as not compatible" : "Not reported by the provider"}</dd>
        </div>
      </dl>
      {model.inferenceProviders && model.inferenceProviders.length > 0 && (
        <table className="table small-table">
          <caption>Inference providers reported by Hugging Face</caption>
          <thead>
            <tr>
              <th scope="col">Provider</th>
              <th scope="col">Status</th>
              <th scope="col">Context</th>
              <th scope="col">Structured output</th>
            </tr>
          </thead>
          <tbody>
            {model.inferenceProviders.map((p) => (
              <tr key={p.name}>
                <th scope="row">{p.name}</th>
                <td>{p.status}</td>
                <td>{p.contextLength ? formatCount(p.contextLength) : "—"}</td>
                <td>{p.supportsStructuredOutput === undefined ? "—" : p.supportsStructuredOutput ? "Yes" : "No"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {model.notes.map((note) => (
        <p key={note} className="muted small">
          {note}
        </p>
      ))}
    </div>
  );
}

export function ModelPicker({ draft, value, saved, onChange }: { draft: Credentials; value: string; saved: string; onChange: (model: string) => void }) {
  const provider = draft.provider;
  const key = draft.keys[provider] ?? "";
  const [catalogue, setCatalogue] = useState<ModelCatalogue | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState("");
  const [query, setQuery] = useState("");
  const [reload, setReload] = useState(0);
  const listId = useId();
  const meta = PROVIDERS[provider];

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setFailed("");
    const timer = setTimeout(() => {
      api
        .models({ ...draft, provider }, controller.signal)
        .then((result) => setCatalogue(result))
        .catch((error: unknown) => {
          if (controller.signal.aborted) return;
          setCatalogue(null);
          setFailed(error instanceof Error ? error.message : "The model list could not be loaded.");
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 350);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [provider, key, reload]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const all = catalogue?.models ?? [];
    return needle ? all.filter((m) => `${m.id} ${m.name} ${m.description ?? ""}`.toLowerCase().includes(needle)) : all;
  }, [catalogue, query]);

  const selected = catalogue?.models.find((m) => m.id === value) ?? null;
  const customValid = MODEL_ID_PATTERN.test(query.trim());
  const typedIsNew = !!query.trim() && !catalogue?.models.some((m) => m.id === query.trim());

  return (
    <div className="model-picker">
      <div className="picker-head">
        <label htmlFor={`${listId}-search`}>Model</label>
        <button className="link" type="button" onClick={() => setReload((n) => n + 1)} disabled={loading}>
          Refresh list
        </button>
      </div>
      <p className="muted small" role="status">
        {value ? (
          <>
            Selected: <strong>{value}</strong>
            {value === saved ? " (saved default)" : saved ? ` — your saved default is ${saved} until you save` : " — not saved yet"}
          </>
        ) : (
          "No model selected yet."
        )}
      </p>
      <input
        id={`${listId}-search`}
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={`Search ${meta.label} models, or paste a model ID`}
        autoComplete="off"
        spellCheck={false}
        aria-controls={listId}
      />
      {loading && <p className="muted small skeleton-line" aria-live="polite">Loading models…</p>}
      {failed && <p className="error" role="alert">{failed}</p>}
      {catalogue?.warning && <p className="notice small">{catalogue.warning}</p>}
      {catalogue && (
        <p className="muted small">
          {catalogue.source === "provider"
            ? `${catalogue.models.length} models reported by ${meta.label}.`
            : "Showing CineCritic's suggested default, not a live list from the provider."}
        </p>
      )}
      {typedIsNew && customValid && (
        <button className="ghost" type="button" onClick={() => onChange(query.trim())}>
          Use “{query.trim()}” as a custom model ID
        </button>
      )}
      {typedIsNew && !customValid && <p className="muted small">Model IDs use letters, numbers and . _ : / @ + - only.</p>}
      <ul id={listId} className="model-list" role="listbox" aria-label={`${meta.label} models`}>
        {filtered.slice(0, SHOWN).map((m) => (
          <li key={m.id} role="option" aria-selected={m.id === value}>
            <button type="button" className={m.id === value ? "model on" : "model"} onClick={() => onChange(m.id)}>
              <span className="model-name">{m.id}</span>
              <span className="model-meta">
                {m.contextLength !== undefined && <span className="muted small">{formatCount(m.contextLength)} ctx</span>}
                <Badge model={m} />
              </span>
            </button>
          </li>
        ))}
      </ul>
      {filtered.length > SHOWN && <p className="muted small">Showing the first {SHOWN} of {filtered.length}. Refine your search to see more.</p>}
      {catalogue && !filtered.length && !loading && <p className="muted small">No models match your search.</p>}
      {meta.notes.length > 0 && (
        <ul className="notes small muted">
          {meta.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
      {value && <Details model={selected} custom={value} />}
    </div>
  );
}
