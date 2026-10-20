import { test } from "node:test";
import assert from "node:assert/strict";
import { applyEvent, createRun, elapsedMs, finishRun, isRetryEligible, parseStreamLine, stageSummary, trimRuns, type PipelineEvent } from "../shared/pipeline";
import { redact, toAppError, AppError } from "../server/errors";

const event = (seq: number, stageId: string, status: PipelineEvent["status"], extra: Partial<PipelineEvent> = {}): PipelineEvent => ({
  executionId: "r1", operation: "ask", stageId, stageLabel: stageId, status, timestamp: 1000 + seq * 100, seq, message: "", retryCount: 0, ...extra,
});

const fresh = () => createRun({ id: "r1", operation: "ask", label: "Ask", startedAt: 1000, retry: { text: "q" } });

test("events apply in order and duplicates or stale events are ignored", () => {
  let run = fresh();
  run = applyEvent(run, event(1, "validate", "running"));
  run = applyEvent(run, event(2, "validate", "completed"));
  const again = applyEvent(run, event(2, "validate", "failed"));
  assert.equal(again, run);
  assert.equal(applyEvent(run, event(1, "validate", "failed")), run);
  assert.equal(applyEvent(run, { ...event(3, "prepare", "running"), executionId: "other" }), run);
  assert.equal(run.stages[0]!.status, "completed");
  assert.equal(run.stages[0]!.duration, 100);
});

test("retries and progress are tracked per stage", () => {
  let run = fresh();
  run = applyEvent(run, event(1, "inference", "running"));
  run = applyEvent(run, event(2, "inference", "retrying", { retryCount: 1 }));
  run = applyEvent(run, event(3, "inference", "running", { progress: 0.5, retryCount: 1 }));
  const stage = run.stages.find((s) => s.id === "inference")!;
  assert.equal(stage.retryCount, 1);
  assert.equal(stage.progress, 0.5);
});

test("a result completes active stages and skips pending ones; summary counts real stages", () => {
  let run = fresh();
  run = applyEvent(run, event(1, "validate", "completed"));
  run = applyEvent(run, event(2, "inference", "running"));
  run = finishRun(run, { type: "result" }, 5000);
  assert.equal(run.status, "completed");
  assert.equal(run.stages.find((s) => s.id === "inference")!.status, "completed");
  assert.equal(run.stages.find((s) => s.id === "spoiler")!.status, "skipped");
  assert.deepEqual(stageSummary(run), { done: 2, total: 2 });
  assert.equal(elapsedMs(run, 9999), 4000);
  assert.equal(isRetryEligible(run), false);
});

test("errors map to failed, timed out and cancelled and allow retry", () => {
  const error = (code: any) => ({ code, stage: "inference", message: "m", nextStep: "n", retryable: true, reference: "r" });
  for (const [code, status] of [["auth_failed", "failed"], ["timeout", "timed_out"], ["cancelled", "cancelled"]] as const) {
    let run = applyEvent(fresh(), event(1, "inference", "running"));
    run = finishRun(run, { type: "error", error: error(code) }, 3000);
    assert.equal(run.status, status);
    assert.equal(run.stages.find((s) => s.id === "inference")!.status, status);
    assert.equal(isRetryEligible(run), true);
  }
});

test("a finished run ignores late events", () => {
  const run = finishRun(fresh(), { type: "result" }, 2000);
  assert.equal(applyEvent(run, event(1, "validate", "running")), run);
  assert.equal(finishRun(run, { type: "result" }, 3000), run);
});

test("stream lines are validated", () => {
  assert.equal(parseStreamLine("not json"), null);
  assert.equal(parseStreamLine(JSON.stringify({ type: "event", event: { nope: true } })), null);
  assert.equal(parseStreamLine(JSON.stringify({ type: "event", event: event(1, "validate", "running", { progress: 2 }) })), null);
  assert.equal(parseStreamLine(JSON.stringify({ type: "event", event: event(1, "validate", "running") }))?.type, "event");
  assert.deepEqual(parseStreamLine(JSON.stringify({ type: "result", data: { a: 1 } })), { type: "result", data: { a: 1 } });
});

test("history is bounded", () => {
  const runs = Array.from({ length: 50 }, (_, i) => ({ ...fresh(), id: String(i) }));
  assert.equal(trimRuns(runs, 40).length, 40);
});

test("redact removes keys, bearer tokens and common key shapes", () => {
  const text = "Bearer abcdefghijkl and sk-abcdefghij and hf_abcdefghij and AIzaSyabcdefghijk and ?key=zzzzzzz and mysecretvalue";
  const out = redact(text, ["mysecretvalue"]);
  for (const leaked of ["abcdefghijkl", "sk-abcdefghij", "hf_abcdefghij", "AIzaSyabcdefghijk", "zzzzzzz", "mysecretvalue"]) assert.ok(!out.includes(leaked), leaked);
});

test("unknown errors become a generic internal error without details", () => {
  const original = console.error;
  console.error = () => {};
  try {
    const app = toAppError(new Error("boom with secret-key-123"), "inference", ["secret-key-123"]);
    assert.equal(app.code, "internal");
    assert.doesNotMatch(app.message, /boom|secret/);
    assert.equal(toAppError(app, "other").stage, "inference");
    assert.equal(toAppError(new TypeError("fetch failed"), "x").code, "network");
    assert.equal(new AppError("rate_limited").retryable, true);
  } finally {
    console.error = original;
  }
});
