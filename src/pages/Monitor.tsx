import { useState } from "react";
import { elapsedMs, runRetries, stageSummary, type RunStatus } from "../../shared/pipeline";
import { PipelinePanel, RUN_WORDS, modelLabel, seconds } from "../components/Pipeline";
import { cancelRun, clearFinishedRuns, useRuns } from "../pipeline/store";

const FILTERS: (RunStatus | "all")[] = ["all", "running", "completed", "failed", "timed_out", "cancelled"];

export function Monitor() {
  const runs = useRuns();
  const [filter, setFilter] = useState<RunStatus | "all">("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const visible = runs.filter((r) => filter === "all" || r.status === filter);
  const selected = runs.find((r) => r.id === selectedId) ?? visible[0] ?? null;
  const now = Date.now();

  return (
    <div>
      <h2 className="page-title">Pipeline Monitor</h2>
      <p className="muted">Every analysis, search and test you run appears here with its real stages and timings. History stays in this browser only and never includes keys or your prompts.</p>
      <div className="row">
        <label>
          Show
          <select value={filter} onChange={(e) => setFilter(e.target.value as RunStatus | "all")}>
            {FILTERS.map((f) => (
              <option key={f} value={f}>
                {f === "all" ? "All runs" : RUN_WORDS[f]}
              </option>
            ))}
          </select>
        </label>
        <button className="ghost" type="button" onClick={clearFinishedRuns} disabled={!runs.some((r) => r.status !== "running")}>
          Clear finished runs
        </button>
      </div>

      {!runs.length && (
        <div className="empty panel">
          <p>No runs yet.</p>
          <p className="muted">Analyze a film and its pipeline will show up here.</p>
        </div>
      )}
      {runs.length > 0 && !visible.length && <p className="muted">No runs match this filter.</p>}

      {visible.length > 0 && (
        <div className="monitor">
          <ul className="run-list" aria-label="Runs">
            {visible.map((r) => {
              const summary = stageSummary(r);
              return (
                <li key={r.id}>
                  <button type="button" className={selected?.id === r.id ? "run on" : "run"} onClick={() => setSelectedId(r.id)} aria-current={selected?.id === r.id}>
                    <span className="run-title">{r.label}</span>
                    <span className={`pill ${r.status}`}>{RUN_WORDS[r.status]}</span>
                    <span className="muted small">
                      {new Date(r.startedAt).toLocaleTimeString()} · {seconds(elapsedMs(r, now))} · {summary.done}/{summary.total} stages
                      {runRetries(r) > 0 ? ` · ${runRetries(r)} retries` : ""}
                    </span>
                    {modelLabel(r) && <span className="muted small">{modelLabel(r)}</span>}
                  </button>
                </li>
              );
            })}
          </ul>
          {selected && <PipelinePanel run={selected} onCancel={() => cancelRun(selected.id)} />}
        </div>
      )}
    </div>
  );
}
