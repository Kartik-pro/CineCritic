import { useSyncExternalStore } from "react";
import type { ErrorCode, ErrorInfo, OperationType, Outcome, RetryRequest, RunRecord } from "../../shared/pipeline";
import { applyEvent, createRun, finishRun, parseStreamLine, trimRuns } from "../../shared/pipeline";
import { savedHeaders } from "../api";

const HISTORY_KEY = "cc.runs";
const HISTORY_LIMIT = 40;
const CLIENT_TIMEOUT_MS = 75_000;

export class RunFailure extends Error {
  constructor(readonly info: ErrorInfo) {
    super(info.message);
  }
}

export interface RunSpec {
  operation: OperationType;
  label: string;
  path: string;
  body: Record<string, unknown>;
  retry?: RetryRequest;
  headers?: Record<string, string>;
  ownAuth?: boolean;
}

export interface Started<T> {
  id: string;
  promise: Promise<T>;
}

type Listener = () => void;

const listeners = new Set<Listener>();
const controllers = new Map<string, AbortController>();
const inflight = new Map<string, Started<never>>();

const interrupted = (id: string): ErrorInfo => ({
  code: "cancelled",
  stage: "run",
  message: "This run was interrupted when the page was closed or reloaded.",
  nextStep: "Start it again from its page.",
  retryable: true,
  reference: `${id.slice(0, 8)}-interrupted`,
});

function loadHistory(): RunRecord[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((r): r is RunRecord => !!r && typeof r.id === "string" && Array.isArray(r.stages) && typeof r.startedAt === "number")
      .map((r) => (r.status === "running" ? finishRun(r, { type: "error", error: interrupted(r.id) }, r.endedAt ?? Date.now()) : r))
      .slice(0, HISTORY_LIMIT);
  } catch {
    return [];
  }
}

let runs: RunRecord[] = loadHistory();

function persist(): void {
  try {
    const safe = runs.filter((r) => r.status !== "running").map(({ retry: _retry, ...rest }) => rest);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(safe));
  } catch {
    return;
  }
}

function emit(save = false): void {
  if (save) persist();
  for (const listener of listeners) listener();
}

function update(id: string, change: (run: RunRecord) => RunRecord, save = false): void {
  runs = runs.map((r) => (r.id === id ? change(r) : r));
  emit(save);
}

const subscribe = (listener: Listener) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

export const useRuns = (): RunRecord[] => useSyncExternalStore(subscribe, () => runs, () => runs);

export function clearFinishedRuns(): void {
  runs = runs.filter((r) => r.status === "running");
  emit(true);
}

export function cancelRun(id: string): void {
  controllers.get(id)?.abort();
}

function failure(id: string, code: ErrorCode, message: string, nextStep: string, retryable: boolean, stage = "run"): ErrorInfo {
  return { code, stage, message, nextStep, retryable, reference: `${id.slice(0, 8)}-${code}` };
}

async function httpFailure(id: string, response: Response): Promise<ErrorInfo> {
  const body: unknown = await response.json().catch(() => null);
  const data = (body && typeof body === "object" ? body : {}) as { error?: unknown; nextStep?: unknown; code?: unknown };
  const message = typeof data.error === "string" ? data.error : `The server responded with status ${response.status}.`;
  const nextStep = typeof data.nextStep === "string" ? data.nextStep : "Retry. If it keeps failing, check the deployment logs.";
  const known = response.status === 401 ? "auth_failed" : response.status === 404 ? "not_found" : "internal";
  return failure(id, known, message, nextStep, response.status >= 500);
}

function abortFailure(id: string, controller: AbortController): ErrorInfo {
  const reason: unknown = controller.signal.reason;
  const timedOut = reason instanceof DOMException && reason.name === "TimeoutError";
  return timedOut
    ? failure(id, "timeout", "The server took too long to respond.", "Retry, or choose a faster model in Settings.", true)
    : failure(id, "cancelled", "The operation was cancelled.", "Start it again when you are ready.", true);
}

async function execute<T>(id: string, spec: RunSpec, controller: AbortController): Promise<T> {
  const timer = setTimeout(() => controller.abort(new DOMException("timeout", "TimeoutError")), CLIENT_TIMEOUT_MS);
  let outcome: Outcome | null = null;
  let data: unknown;
  try {
    const headers = { "content-type": "application/json", ...(spec.ownAuth ? {} : savedHeaders()), ...spec.headers };
    const response = await fetch(spec.path, {
      method: "POST",
      headers,
      body: JSON.stringify({ ...spec.body, executionId: id }),
      signal: controller.signal,
    });
    if (!response.ok || !response.body || !(response.headers.get("content-type") ?? "").includes("ndjson")) {
      outcome = { type: "error", error: await httpFailure(id, response) };
    } else {
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      const handle = (line: string) => {
        const message = parseStreamLine(line);
        if (!message) return;
        if (message.type === "event") update(id, (r) => applyEvent(r, message.event));
        else if (message.type === "result") {
          data = message.data;
          outcome = { type: "result" };
        } else outcome = { type: "error", error: message.error };
      };
      for (;;) {
        const chunk = await reader.read();
        if (chunk.value) buffer += decoder.decode(chunk.value, { stream: !chunk.done });
        let newline = buffer.indexOf("\n");
        while (newline >= 0) {
          const line = buffer.slice(0, newline).trim();
          buffer = buffer.slice(newline + 1);
          if (line) handle(line);
          newline = buffer.indexOf("\n");
        }
        if (chunk.done) break;
      }
      if (buffer.trim()) handle(buffer.trim());
      outcome ??= {
        type: "error",
        error: failure(id, "network", "The connection closed before the result arrived.", "Check your connection and retry.", true),
      };
    }
  } catch (error) {
    const info = controller.signal.aborted
      ? abortFailure(id, controller)
      : failure(id, "network", error instanceof TypeError ? "Could not reach the server." : "The request failed.", "Check your connection and retry.", true);
    outcome = { type: "error", error: info };
  } finally {
    clearTimeout(timer);
  }
  const finalOutcome: Outcome = outcome ?? { type: "result" };
  update(id, (r) => finishRun(r, finalOutcome, Date.now()), true);
  if (finalOutcome.type === "error") throw new RunFailure(finalOutcome.error);
  return data as T;
}

export function startRun<T>(spec: RunSpec): Started<T> {
  const signature = `${spec.operation}|${spec.path}|${JSON.stringify(spec.body)}|${JSON.stringify(spec.headers ?? {})}`;
  const existing = inflight.get(signature);
  if (existing) return existing as unknown as Started<T>;
  const id = crypto.randomUUID();
  runs = trimRuns(
    [createRun({ id, operation: spec.operation, label: spec.label, startedAt: Date.now(), ...(spec.retry ? { retry: spec.retry } : {}) }), ...runs],
    HISTORY_LIMIT,
  );
  const controller = new AbortController();
  controllers.set(id, controller);
  emit();
  const promise = execute<T>(id, spec, controller).finally(() => {
    inflight.delete(signature);
    controllers.delete(id);
  });
  const started: Started<T> = { id, promise };
  inflight.set(signature, started as unknown as Started<never>);
  return started;
}
