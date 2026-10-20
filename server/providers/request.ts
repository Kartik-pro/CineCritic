import { PROVIDERS, type ProviderId } from "../../shared/providers.js";
import { AppError, toAppError } from "../errors.js";

export interface RequestOptions {
  method?: "GET" | "POST";
  headers?: Record<string, string>;
  body?: unknown;
  signal?: AbortSignal;
  timeoutMs: number;
}

export function httpFailure(status: number, provider: ProviderId): AppError {
  const label = PROVIDERS[provider].label;
  const hf = provider === "huggingface";
  if (status === 401)
    return new AppError("auth_failed", {
      message: `${label} rejected the API key.`,
      nextStep: hf
        ? "Check the token in Settings. It needs the “Make calls to Inference Providers” permission."
        : "Check the key in Settings.",
    });
  if (status === 403)
    return new AppError("permission_denied", {
      message: `${label} says this key is not allowed to make this request.`,
      nextStep: hf
        ? "Use a fine-grained token with the “Make calls to Inference Providers” permission."
        : "Check the key's permissions with the provider.",
    });
  if (status === 402) return new AppError("quota_exceeded", { message: `${label} reports that credits or quota are used up.` });
  if (status === 404) return new AppError("model_not_found", { message: `${label} could not find that model.` });
  if (status === 400 || status === 422)
    return new AppError("unsupported_model", {
      message: `${label} rejected this request for the selected model.`,
      nextStep: hf
        ? "The model may not be served by an inference provider for chat. Choose another model in Settings."
        : "The model may not support this task. Choose another model in Settings.",
    });
  if (status === 408 || status === 504) return new AppError("timeout", { message: `${label} timed out.` });
  if (status === 429) return new AppError("rate_limited", { message: `${label} is rate-limiting requests.` });
  return new AppError("provider_unavailable", { message: `${label} is temporarily unavailable.` });
}

export async function providerRequest(
  url: string,
  options: RequestOptions,
  provider: ProviderId,
  secrets: readonly string[],
): Promise<unknown> {
  const timeout = AbortSignal.timeout(options.timeoutMs);
  const signal = options.signal ? AbortSignal.any([timeout, options.signal]) : timeout;
  let response: Response;
  try {
    response = await fetch(url, {
      method: options.method ?? "POST",
      headers: { ...(options.body === undefined ? {} : { "content-type": "application/json" }), ...options.headers },
      ...(options.body === undefined ? {} : { body: JSON.stringify(options.body) }),
      signal,
    });
  } catch (error) {
    if (error instanceof AppError) throw error;
    const mapped = toAppError(error, "", secrets);
    if (mapped.code === "network") {
      throw new AppError("network", { message: `Could not reach ${PROVIDERS[provider].label}.` });
    }
    throw mapped;
  }
  if (!response.ok) throw httpFailure(response.status, provider);
  try {
    return await response.json();
  } catch {
    throw new AppError("malformed_output", { message: `${PROVIDERS[provider].label} returned an unreadable response.` });
  }
}

export const asRecord = (value: unknown): Record<string, any> =>
  typeof value === "object" && value !== null ? (value as Record<string, any>) : {};

export const asNumber = (value: unknown): number | undefined =>
  typeof value === "number" && Number.isFinite(value) && value > 0 ? value : undefined;
