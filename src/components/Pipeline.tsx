import { useEffect, useState } from "react";
import { elapsedMs, runRetries, stageSummary, type RunRecord, type RunStatus, type StageState, type StageStatus } from "../../shared/pipeline";
import { PROVIDERS, isProviderId } from "../../shared/providers";
import { useApp } from "../state";

const MARKS: Record<StageStatus, string> = {
  pending: "○",
  running: "●",
  retrying: "↻",
  completed: "✓",
  failed: "✕",
  skipped: "–",
  cancelled: "■",
  timed_out: "!",
};

const STAGE_WORDS: Record<StageStatus, string> = {
  pending: "Waiting",
  running: "In progress",
  retrying: "Retrying",
  completed: "Completed",
  failed: "Failed",
  skipped: "Skipped",
  cancelled: "Cancelled",
  timed_out: "Timed out",
};

export const RUN_WORDS: Record<RunStatus, string> = {
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
  timed_out: "Timed out",
};

const SETTINGS_CODES = ["missing_key", "auth_failed", "permission_denied", "model_not_found", "unsupported_model", "quota_exceeded"];

export const seconds = (ms: number): string => `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)}s`;

export function modelLabel(run: RunRecord): string {
  if (!run.provider) return "";
  const name = isProviderId(run.provider) ? PROVIDERS[run.provider].label : run.provider;
  return run.model ? `${name} · ${run.model}` : name;
}

function useNow(active: boolean): number {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(timer);
  }, [active]);
  return now;
}

function StageRow({ stage, now }: { stage: StageState; now: number }) {
  const live = stage.status === "running" || stage.status === "retrying";
  const time = stage.duration ?? (live && stage.startedAt ? now - stage.startedAt : undefined);
  return (
    <li className={`stage ${stage.status}`}>
      <span className="mark" aria-hidden="true">
        {MARKS[stage.status]}
      </span>
      <div className="stage-body">
        <div className="stage-head">
          <span className="stage-label">{stage.label}</span>
          <span className="stage-state">
            <span className="sr-only">{STAGE_WORDS[stage.status]}. </span>
            {stage.status !== "completed" && stage.status !== "pending" && <span aria-hidden="true">{STAGE_WORDS[stage.status]}</span>}
            {time !== undefined && stage.status !== "pending" && stage.status !== "skipped" ? ` ${seconds(time)}` : ""}
            {stage.retryCount > 0 ? ` · ${stage.retryCount} ${stage.retryCount === 1 ? "retry" : "retries"}` : ""}
          </span>
        </div>
        {stage.message && stage.status !== "pending" && <p className="stage-msg">{stage.message}</p>}
        {live && stage.progress !== undefined && <progress className="stage-bar" value={stage.progress} max={1} aria-label={`${stage.label} progress`} />}
      </div>
    </li>
  );
}

export function ErrorDetails({ run, onRetry }: { run: RunRecord; onRetry?: () => void }) {
  const { go } = useApp();
  const error = run.error;
  if (!error) return null;
  return (
    <div className="pipe-error" role="alert">
      <p className="pipe-error-title">{error.message}</p>
      <p>{error.nextStep}</p>
      <p className="muted small">
        Reference <code>{error.reference}</code>
        {error.stage && error.stage !== "run" ? ` · stage: ${run.stages.find((s) => s.id === error.stage)?.label ?? error.stage}` : ""}
      </p>
      <div className="row">
        {onRetry && error.retryable && (
          <button className="primary" type="button" onClick={onRetry}>
            Retry
          </button>
        )}
        {SETTINGS_CODES.includes(error.code) && (
          <button className="ghost" type="button" onClick={() => go("settings")}>
            Open Settings
          </button>
        )}
      </div>
    </div>
  );
}

export function PipelinePanel({ run, onCancel, onRetry }: { run: RunRecord; onCancel?: () => void; onRetry?: () => void }) {
  const running = run.status === "running";
  const now = useNow(running);
  const summary = stageSummary(run);
  const current = run.stages.find((s) => s.status === "running" || s.status === "retrying");
  const retries = runRetries(run);
  return (
    <section className={`pipe ${run.status}`} aria-label={`${run.label} pipeline`}>
      <header className="pipe-head">
        <div>
          <h3>{run.label}</h3>
          <p className="muted small">
            {RUN_WORDS[run.status]} · {summary.done} of {summary.total} stages · {seconds(elapsedMs(run, now))}
            {retries > 0 ? ` · ${retries} ${retries === 1 ? "retry" : "retries"}` : ""}
            {modelLabel(run) ? ` · ${modelLabel(run)}` : ""}
          </p>
        </div>
        {running && onCancel && (
          <button className="ghost" type="button" onClick={onCancel}>
            Cancel
          </button>
        )}
      </header>
      <ol className="stages">
        {run.stages.map((stage) => (
          <StageRow key={stage.id} stage={stage} now={now} />
        ))}
      </ol>
      <p className="sr-only" role="status" aria-live="polite">
        {running ? (current ? `${current.label}. ${current.message}` : "Starting") : RUN_WORDS[run.status]}
      </p>
      <ErrorDetails run={run} {...(onRetry ? { onRetry } : {})} />
    </section>
  );
}

export function RunPanel({ run, onCancel, onRetry }: { run: RunRecord | null; onCancel?: () => void; onRetry?: () => void }) {
  if (!run) return null;
  if (run.status !== "completed") return <PipelinePanel run={run} {...(onCancel ? { onCancel } : {})} {...(onRetry ? { onRetry } : {})} />;
  return (
    <details className="pipe-done">
      <summary>
        {run.label} completed in {seconds(elapsedMs(run, Date.now()))}
        {modelLabel(run) ? ` · ${modelLabel(run)}` : ""} — view pipeline
      </summary>
      <PipelinePanel run={run} />
    </details>
  );
}
