import type { ModelInfo } from "../../shared/providers.js";
import type { ChatMessage } from "../../shared/types.js";

export interface GenerateArgs {
  key: string;
  model: string;
  system: string;
  messages: ChatMessage[];
  json: boolean;
  maxTokens?: number;
  signal: AbortSignal;
  timeoutMs: number;
  secrets: readonly string[];
}

export interface GenerateResult {
  text: string;
  inputTokens?: number;
  outputTokens?: number;
}

export interface ListArgs {
  key: string;
  signal: AbortSignal;
  secrets: readonly string[];
}

export interface ProviderAdapter {
  needsKeyToList: boolean;
  generate(args: GenerateArgs): Promise<GenerateResult>;
  list(args: ListArgs): Promise<ModelInfo[]>;
}
