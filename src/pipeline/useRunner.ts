import { useCallback, useState } from "react";
import type { RunRecord } from "../../shared/pipeline";
import { RunFailure, cancelRun, useRuns, type Started } from "./store";

async function track<T>(started: Started<T>, select: (id: string | null) => void): Promise<T | undefined> {
  select(started.id);
  try {
    return await started.promise;
  } catch (error) {
    if (error instanceof RunFailure) return undefined;
    throw error;
  }
}

export function useRunner(): {
  run: RunRecord | null;
  busy: boolean;
  start: <T>(started: Started<T>) => Promise<T | undefined>;
  cancel: () => void;
  reset: () => void;
} {
  const runs = useRuns();
  const [id, setId] = useState<string | null>(null);
  const run = id ? (runs.find((r) => r.id === id) ?? null) : null;
  const start = useCallback(<T,>(started: Started<T>) => track(started, setId), []);
  const cancel = useCallback(() => {
    if (id) cancelRun(id);
  }, [id]);
  const reset = useCallback(() => setId(null), []);
  return { run, busy: run?.status === "running", start, cancel, reset };
}
