import type { Credentials } from "../keys";
import { authHeaders } from "../keys";
import { OPERATION_LABELS } from "../../shared/pipeline";
import type { Analysis, BattleResponse, ChatMessage, ConnectionResult, CritiqueResponse, Pick } from "../../shared/types";
import type { Options, Target } from "../api";
import { startRun } from "./store";

export type { ConnectionResult };

export const operations = {
  critique: (target: Target, options: Options) =>
    startRun<CritiqueResponse>({
      operation: "critique",
      label: OPERATION_LABELS.critique,
      path: "/api/critique",
      body: { ...target, ...options },
      retry: { target },
    }),
  discover: (text: string) =>
    startRun<{ picks: Pick[] }>({
      operation: "discover",
      label: OPERATION_LABELS.discover,
      path: "/api/discover",
      body: { text },
      retry: { text },
    }),
  ask: (question: string, history: ChatMessage[], analysis: Analysis | null, options: Options) =>
    startRun<{ answer: string }>({
      operation: "ask",
      label: OPERATION_LABELS.ask,
      path: "/api/ask",
      body: { question, history, analysis, ...options },
      retry: { text: question },
    }),
  battle: (a: { analysis?: Analysis; id?: number; query?: string }, b: { analysis?: Analysis; id?: number; query?: string }, options: Options) =>
    startRun<BattleResponse>({
      operation: "battle",
      label: OPERATION_LABELS.battle,
      path: "/api/battle",
      body: { a, b, ...options },
    }),
  connection: (draft: Credentials) =>
    startRun<ConnectionResult>({
      operation: "connection",
      label: OPERATION_LABELS.connection,
      path: "/api/connection",
      body: {},
      headers: authHeaders(draft, { includeTmdb: false }),
      ownAuth: true,
    }),
};
