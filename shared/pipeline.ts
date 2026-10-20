export const OPERATION_TYPES = ["critique", "discover", "ask", "battle", "connection"] as const;
export type OperationType = (typeof OPERATION_TYPES)[number];

export const OPERATION_LABELS: Record<OperationType, string> = {
  critique: "Film critique",
  discover: "Film discovery",
  ask: "Ask the Critic",
  battle: "Movie battle",
  connection: "Connection test",
};

export interface StageDef {
  id: string;
  label: string;
}

export const STAGES: Record<OperationType, readonly StageDef[]> = {
  critique: [
    { id: "validate", label: "Validate request" },
    { id: "prepare", label: "Prepare AI provider" },
    { id: "lookup", label: "Find film on TMDB" },
    { id: "details", label: "Retrieve film data" },
    { id: "inference", label: "Generate analysis" },
    { id: "validate_output", label: "Validate AI output" },
    { id: "spoiler", label: "Apply spoiler protection" },
    { id: "finalize", label: "Prepare results" },
  ],
  discover: [
    { id: "validate", label: "Validate request" },
    { id: "prepare", label: "Prepare AI provider" },
    { id: "inference", label: "Generate suggestions" },
    { id: "validate_output", label: "Validate AI output" },
    { id: "verify", label: "Verify films on TMDB" },
    { id: "finalize", label: "Prepare results" },
  ],
  ask: [
    { id: "validate", label: "Validate question" },
    { id: "prepare", label: "Prepare AI provider" },
    { id: "inference", label: "Generate answer" },
    { id: "spoiler", label: "Apply spoiler protection" },
    { id: "finalize", label: "Prepare results" },
  ],
  battle: [
    { id: "validate", label: "Validate request" },
    { id: "prepare", label: "Prepare AI provider" },
    { id: "resolve", label: "Resolve films" },
    { id: "analyze", label: "Analyse both films" },
    { id: "compare", label: "Compare scores" },
    { id: "narrative", label: "Write comparison" },
    { id: "finalize", label: "Prepare results" },
  ],
  connection: [
    { id: "validate", label: "Validate settings" },
    { id: "prepare", label: "Prepare AI provider" },
    { id: "auth", label: "Check credentials" },
    { id: "inference", label: "Test model response" },
    { id: "finalize", label: "Summarise" },
  ],
};

export const ERROR_CODES = [
  "invalid_input",
  "missing_key",
  "auth_failed",
  "permission_denied",
  "quota_exceeded",
  "rate_limited",
  "timeout",
  "network",
  "model_not_found",
  "unsupported_model",
  "empty_response",
  "malformed_output",
  "provider_unavailable",
  "tmdb_error",
  "not_found",
  "cancelled",
  "internal",
] as const;
export type ErrorCode = (typeof ERROR_CODES)[number];

export type StageStatus =
  | "pending"
  | "running"
  | "retrying"
  | "completed"
  | "failed"
  | "skipped"
  | "cancelled"
  | "timed_out";

export type RunStatus = "running" | "completed" | "failed" | "cancelled" | "timed_out";

export interface ErrorInfo {
  code: ErrorCode;
  stage: string;
  message: string;
  nextStep: string;
  retryable: boolean;
  reference: string;
}

export interface PipelineEvent {
  executionId: string;
  operation: OperationType;
  stageId: string;
  stageLabel: string;
  status: StageStatus;
  timestamp: number;
  seq: number;
  message: string;
  retryCount: number;
  progress?: number;
  duration?: number;
  errorCode?: ErrorCode;
  provider?: string;
  model?: string;
}

export type StreamMessage =
  | { type: "event"; event: PipelineEvent }
  | { type: "result"; data: unknown }
  | { type: "error"; error: ErrorInfo };

export interface StageState {
  id: string;
  label: string;
  status: StageStatus;
  message: string;
  retryCount: number;
  startedAt?: number;
  endedAt?: number;
  duration?: number;
  progress?: number;
  errorCode?: ErrorCode;
}

export interface RetryRequest {
  target?: { id?: number; query?: string };
  text?: string;
}

export interface RunRecord {
  id: string;
  operation: OperationType;
  label: string;
  status: RunStatus;
  startedAt: number;
  endedAt?: number;
  stages: StageState[];
  lastSeq: number;
  provider?: string;
  model?: string;
  error?: ErrorInfo;
  retry?: RetryRequest;
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const STAGE_STATUSES: readonly string[] = [
  "pending",
  "running",
  "retrying",
  "completed",
  "failed",
  "skipped",
  "cancelled",
  "timed_out",
];

export function isPipelineEvent(value: unknown): value is PipelineEvent {
  return (
    isRecord(value) &&
    typeof value.executionId === "string" &&
    (OPERATION_TYPES as readonly string[]).includes(value.operation as string) &&
    typeof value.stageId === "string" &&
    typeof value.stageLabel === "string" &&
    typeof value.status === "string" &&
    STAGE_STATUSES.includes(value.status) &&
    typeof value.timestamp === "number" &&
    typeof value.seq === "number" &&
    typeof value.message === "string" &&
    typeof value.retryCount === "number" &&
    (value.progress === undefined || (typeof value.progress === "number" && value.progress >= 0 && value.progress <= 1))
  );
}

export function isErrorInfo(value: unknown): value is ErrorInfo {
  return (
    isRecord(value) &&
    (ERROR_CODES as readonly string[]).includes(value.code as string) &&
    typeof value.stage === "string" &&
    typeof value.message === "string" &&
    typeof value.nextStep === "string" &&
    typeof value.retryable === "boolean" &&
    typeof value.reference === "string"
  );
}

export function parseStreamLine(line: string): StreamMessage | null {
  let data: unknown;
  try {
    data = JSON.parse(line);
  } catch {
    return null;
  }
  if (!isRecord(data)) return null;
  if (data.type === "event" && isPipelineEvent(data.event)) return { type: "event", event: data.event };
  if (data.type === "result") return { type: "result", data: data.data };
  if (data.type === "error" && isErrorInfo(data.error)) return { type: "error", error: data.error };
  return null;
}

export function createRun(input: {
  id: string;
  operation: OperationType;
  label: string;
  startedAt: number;
  retry?: RetryRequest;
}): RunRecord {
  return {
    id: input.id,
    operation: input.operation,
    label: input.label,
    status: "running",
    startedAt: input.startedAt,
    stages: STAGES[input.operation].map((s) => ({ id: s.id, label: s.label, status: "pending", message: "", retryCount: 0 })),
    lastSeq: 0,
    ...(input.retry ? { retry: input.retry } : {}),
  };
}

const TERMINAL: readonly StageStatus[] = ["completed", "failed", "skipped", "cancelled", "timed_out"];
const ACTIVE: readonly StageStatus[] = ["running", "retrying"];

function updateStage(stage: StageState, event: PipelineEvent): StageState {
  if (event.status === "pending") return stage.status === "pending" ? { ...stage, label: event.stageLabel || stage.label } : stage;
  const next: StageState = {
    ...stage,
    label: event.stageLabel || stage.label,
    status: event.status,
    message: event.message,
    retryCount: Math.max(stage.retryCount, event.retryCount),
  };
  if (event.status === "running" && !ACTIVE.includes(stage.status)) {
    next.startedAt = event.timestamp;
    delete next.endedAt;
    delete next.duration;
    delete next.errorCode;
  }
  if (event.status === "retrying" && next.startedAt === undefined) next.startedAt = event.timestamp;
  if (event.progress !== undefined) next.progress = event.progress;
  if (TERMINAL.includes(event.status)) {
    next.endedAt = event.timestamp;
    const duration = event.duration ?? (next.startedAt !== undefined ? event.timestamp - next.startedAt : undefined);
    if (duration !== undefined) next.duration = duration;
    if (event.errorCode) next.errorCode = event.errorCode;
    if (event.status === "completed" && next.progress !== undefined) next.progress = 1;
  }
  return next;
}

export function applyEvent(run: RunRecord, event: PipelineEvent): RunRecord {
  if (event.executionId !== run.id || event.seq <= run.lastSeq || run.status !== "running") return run;
  const known = run.stages.some((s) => s.id === event.stageId);
  const base = known
    ? run.stages
    : [...run.stages, { id: event.stageId, label: event.stageLabel, status: "pending" as StageStatus, message: "", retryCount: 0 }];
  return {
    ...run,
    stages: base.map((s) => (s.id === event.stageId ? updateStage(s, event) : s)),
    lastSeq: event.seq,
    ...(event.provider ? { provider: event.provider } : {}),
    ...(event.model ? { model: event.model } : {}),
  };
}

export type Outcome = { type: "result" } | { type: "error"; error: ErrorInfo };

export function finishRun(run: RunRecord, outcome: Outcome, now: number): RunRecord {
  if (run.status !== "running") return run;
  if (outcome.type === "result") {
    return {
      ...run,
      status: "completed",
      endedAt: now,
      stages: run.stages.map((s) =>
        s.status === "pending"
          ? { ...s, status: "skipped", message: s.message || "Not needed" }
          : ACTIVE.includes(s.status)
            ? { ...s, status: "completed", endedAt: now }
            : s,
      ),
    };
  }
  const { error } = outcome;
  const status: RunStatus = error.code === "cancelled" ? "cancelled" : error.code === "timeout" ? "timed_out" : "failed";
  const stageStatus: StageStatus = status === "cancelled" ? "cancelled" : status === "timed_out" ? "timed_out" : "failed";
  return {
    ...run,
    status,
    endedAt: now,
    error,
    stages: run.stages.map((s) =>
      ACTIVE.includes(s.status)
        ? { ...s, status: stageStatus, endedAt: now, errorCode: error.code, message: s.id === error.stage ? error.message : s.message }
        : s.status === "pending"
          ? { ...s, status: "skipped", message: "Not reached" }
          : s,
    ),
  };
}

export function trimRuns(runs: RunRecord[], max: number): RunRecord[] {
  return runs.length > max ? runs.slice(0, max) : runs;
}

export const runRetries = (run: RunRecord): number => run.stages.reduce((sum, s) => sum + s.retryCount, 0);

export function stageSummary(run: RunRecord): { done: number; total: number } {
  const relevant = run.stages.filter((s) => s.status !== "skipped");
  return { done: relevant.filter((s) => s.status === "completed").length, total: relevant.length };
}

export const elapsedMs = (run: RunRecord, now: number): number => (run.endedAt ?? now) - run.startedAt;

export const isRetryEligible = (run: RunRecord): boolean =>
  !!run.retry && (run.status === "failed" || run.status === "timed_out" || run.status === "cancelled");
