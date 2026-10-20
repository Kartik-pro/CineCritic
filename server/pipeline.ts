import { STAGES, type ErrorCode, type OperationType, type PipelineEvent, type StageStatus, type StreamMessage } from "../shared/pipeline.js";
import type { Env } from "./ai.js";
import { AppError, toAppError, toErrorInfo } from "./errors.js";
import { readJson } from "./http.js";
import { requestKeys } from "./keys.js";

export const DEADLINE_MS = 55_000;

export class Tracker {
  current = "";
  private seq = 0;
  private started = new Map<string, number>();
  private retries = new Map<string, number>();
  private provider = "";
  private model = "";

  constructor(
    readonly executionId: string,
    readonly operation: OperationType,
    private emit: (message: StreamMessage) => void,
    private secrets: readonly string[],
  ) {}

  setModel(provider: string, model: string): void {
    this.provider = provider;
    this.model = model;
  }

  private send(
    stageId: string,
    status: StageStatus,
    message: string,
    extra: { progress?: number; duration?: number; errorCode?: ErrorCode } = {},
  ): void {
    const label = STAGES[this.operation].find((s) => s.id === stageId)?.label ?? stageId;
    const event: PipelineEvent = {
      executionId: this.executionId,
      operation: this.operation,
      stageId,
      stageLabel: label,
      status,
      timestamp: Date.now(),
      seq: ++this.seq,
      message,
      retryCount: this.retries.get(stageId) ?? 0,
      ...(extra.progress !== undefined ? { progress: Math.min(1, Math.max(0, extra.progress)) } : {}),
      ...(extra.duration !== undefined ? { duration: extra.duration } : {}),
      ...(extra.errorCode ? { errorCode: extra.errorCode } : {}),
      ...(this.provider ? { provider: this.provider } : {}),
      ...(this.model ? { model: this.model } : {}),
    };
    this.emit({ type: "event", event });
  }

  private elapsed(stageId: string): number | undefined {
    const at = this.started.get(stageId);
    return at === undefined ? undefined : Date.now() - at;
  }

  declare(): void {
    for (const stage of STAGES[this.operation]) this.send(stage.id, "pending", "");
  }

  start(stageId: string, message: string): void {
    this.current = stageId;
    this.started.set(stageId, Date.now());
    this.send(stageId, "running", message);
  }

  progress(stageId: string, message: string, fraction: number): void {
    this.send(stageId, "running", message, { progress: fraction });
  }

  retrying(stageId: string, message: string): void {
    this.retries.set(stageId, (this.retries.get(stageId) ?? 0) + 1);
    this.send(stageId, "retrying", message);
  }

  complete(stageId: string, message: string): void {
    const duration = this.elapsed(stageId);
    this.send(stageId, "completed", message, duration !== undefined ? { duration } : {});
  }

  skip(stageId: string, message: string): void {
    this.send(stageId, "skipped", message);
  }

  fail(stageId: string, error: AppError): void {
    const status: StageStatus = error.code === "timeout" ? "timed_out" : error.code === "cancelled" ? "cancelled" : "failed";
    const duration = this.elapsed(stageId);
    this.send(stageId, status, error.message, { errorCode: error.code, ...(duration !== undefined ? { duration } : {}) });
  }

  async stage<T>(
    stageId: string,
    startMessage: string,
    work: () => T | Promise<T>,
    done: string | ((result: T) => string) = "Done",
  ): Promise<T> {
    this.start(stageId, startMessage);
    try {
      const result = await work();
      this.complete(stageId, typeof done === "string" ? done : done(result));
      return result;
    } catch (error) {
      const app = toAppError(error, stageId, this.secrets);
      this.fail(stageId, app);
      throw app;
    }
  }
}

export interface OperationContext {
  body: Record<string, unknown>;
  t: Tracker;
  env: Env;
}

const EXECUTION_ID = /^[A-Za-z0-9-]{8,64}$/;

export function streamOperation(
  req: Request,
  operation: OperationType,
  run: (context: OperationContext) => Promise<unknown>,
): Response {
  const encoder = new TextEncoder();
  const client = new AbortController();
  const keys = requestKeys();
  const secrets = [keys.tmdb, keys.ai].filter(Boolean);
  let closed = false;

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const emit = (message: StreamMessage) => {
        if (closed) return;
        try {
          controller.enqueue(encoder.encode(`${JSON.stringify(message)}\n`));
        } catch {
          closed = true;
        }
      };

      void (async () => {
        const body = await readJson(req);
        const sent = body?.executionId;
        const executionId = typeof sent === "string" && EXECUTION_ID.test(sent) ? sent : crypto.randomUUID();
        const t = new Tracker(executionId, operation, emit, secrets);
        const timeout = AbortSignal.timeout(DEADLINE_MS);
        const signal = AbortSignal.any([client.signal, timeout, req.signal]);
        t.declare();
        try {
          if (!body) throw new AppError("invalid_input", { stage: "validate", message: "The request body was not valid." });
          const data = await run({ body, t, env: { signal, deadline: Date.now() + DEADLINE_MS } });
          emit({ type: "result", data });
        } catch (error) {
          const stage = t.current || "validate";
          const app =
            timeout.aborted && !client.signal.aborted ? new AppError("timeout", { stage }) : toAppError(error, stage, secrets);
          emit({ type: "error", error: toErrorInfo(app, executionId) });
        } finally {
          if (!closed) {
            closed = true;
            try {
              controller.close();
            } catch {
              closed = true;
            }
          }
        }
      })();
    },
    cancel() {
      closed = true;
      client.abort();
    },
  });

  return new Response(stream, {
    headers: {
      "content-type": "application/x-ndjson; charset=utf-8",
      "cache-control": "no-store",
      "x-accel-buffering": "no",
    },
  });
}
