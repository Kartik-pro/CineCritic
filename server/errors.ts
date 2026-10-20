import type { ErrorCode, ErrorInfo } from "../shared/pipeline.js";

export class HttpError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

interface CatalogEntry {
  status: number;
  message: string;
  nextStep: string;
  retryable: boolean;
}

const CATALOG: Record<ErrorCode, CatalogEntry> = {
  invalid_input: { status: 400, message: "The request was not valid.", nextStep: "Check your input and try again.", retryable: false },
  missing_key: { status: 401, message: "An API key is missing.", nextStep: "Add the key in Settings.", retryable: false },
  auth_failed: { status: 401, message: "The provider rejected the API key.", nextStep: "Check the key in Settings.", retryable: false },
  permission_denied: { status: 403, message: "The key does not have permission for this request.", nextStep: "Check the key's permissions in Settings.", retryable: false },
  quota_exceeded: { status: 402, message: "The provider reports that credits or quota are used up.", nextStep: "Check your plan or billing with the provider, or choose another model.", retryable: false },
  rate_limited: { status: 429, message: "The provider is rate-limiting requests.", nextStep: "Wait a moment and retry.", retryable: true },
  timeout: { status: 504, message: "The operation took too long.", nextStep: "Retry, or choose a faster model in Settings.", retryable: true },
  network: { status: 502, message: "A network request failed.", nextStep: "Check your connection and retry.", retryable: true },
  model_not_found: { status: 404, message: "That model was not found.", nextStep: "Choose another model in Settings.", retryable: false },
  unsupported_model: { status: 400, message: "The provider rejected this request for the selected model.", nextStep: "The model may not support this task. Choose another model in Settings.", retryable: false },
  empty_response: { status: 502, message: "The AI returned an empty response.", nextStep: "Retry the operation.", retryable: true },
  malformed_output: { status: 502, message: "The AI returned an unreadable response.", nextStep: "Retry, or choose a model that follows instructions more reliably.", retryable: true },
  provider_unavailable: { status: 503, message: "The provider is temporarily unavailable.", nextStep: "Retry in a moment.", retryable: true },
  tmdb_error: { status: 502, message: "TMDB returned an error.", nextStep: "Retry in a moment.", retryable: true },
  not_found: { status: 404, message: "Nothing matched.", nextStep: "Check the spelling or add the release year.", retryable: false },
  cancelled: { status: 499, message: "The operation was cancelled.", nextStep: "Start it again when you are ready.", retryable: true },
  internal: { status: 500, message: "Something went wrong on the server.", nextStep: "Retry. If it keeps failing, quote the reference below.", retryable: true },
};

export class AppError extends HttpError {
  readonly code: ErrorCode;
  stage: string;
  readonly nextStep: string;
  readonly retryable: boolean;

  constructor(code: ErrorCode, options: { stage?: string; message?: string; nextStep?: string } = {}) {
    const entry = CATALOG[code];
    super(entry.status, options.message ?? entry.message);
    this.code = code;
    this.stage = options.stage ?? "";
    this.nextStep = options.nextStep ?? entry.nextStep;
    this.retryable = entry.retryable;
  }
}

export function redact(text: string, secrets: readonly string[] = []): string {
  let out = text;
  for (const secret of secrets) if (secret && secret.length >= 6) out = out.split(secret).join("[redacted]");
  return out
    .replace(/\b(Bearer\s+)[A-Za-z0-9._~+/=-]{8,}/gi, "$1[redacted]")
    .replace(/\b(sk-[A-Za-z0-9_-]{8,}|hf_[A-Za-z0-9]{8,}|AIza[0-9A-Za-z_-]{10,})/g, "[redacted]")
    .replace(/([?&](?:api_key|key)=)[^&\s]+/gi, "$1[redacted]");
}

export const referenceFor = (executionId: string, code: string): string => `${executionId.slice(0, 8)}-${code}`;

const codeForStatus = (status: number): ErrorCode => {
  if (status === 400) return "invalid_input";
  if (status === 401) return "auth_failed";
  if (status === 403) return "permission_denied";
  if (status === 404) return "not_found";
  if (status === 429) return "rate_limited";
  if (status === 504) return "timeout";
  if (status >= 500) return "provider_unavailable";
  return "internal";
};

const errorName = (error: unknown): string => (typeof error === "object" && error !== null ? String((error as { name?: unknown }).name ?? "") : "");

export function toAppError(error: unknown, stage: string, secrets: readonly string[] = []): AppError {
  if (error instanceof AppError) {
    if (!error.stage) error.stage = stage;
    return error;
  }
  if (error instanceof HttpError) {
    return new AppError(codeForStatus(error.status), { stage, message: redact(error.message, secrets) });
  }
  const name = errorName(error);
  if (name === "TimeoutError") return new AppError("timeout", { stage });
  if (name === "AbortError") return new AppError("cancelled", { stage });
  if (error instanceof TypeError) return new AppError("network", { stage });
  console.error(redact(error instanceof Error ? (error.stack ?? error.message) : String(error), secrets));
  return new AppError("internal", { stage });
}

export function toErrorInfo(error: AppError, executionId: string): ErrorInfo {
  return {
    code: error.code,
    stage: error.stage || "run",
    message: error.message,
    nextStep: error.nextStep,
    retryable: error.retryable,
    reference: referenceFor(executionId, error.code),
  };
}
