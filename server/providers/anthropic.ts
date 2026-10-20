import type { ModelInfo } from "../../shared/providers.js";
import { asNumber, asRecord, providerRequest } from "./request.js";
import type { GenerateArgs, GenerateResult, ListArgs, ProviderAdapter } from "./types.js";

const headers = (key: string) => ({ "x-api-key": key, "anthropic-version": "2023-06-01" });

export const anthropic: ProviderAdapter = {
  needsKeyToList: true,
  async generate(args: GenerateArgs): Promise<GenerateResult> {
    const data = asRecord(
      await providerRequest(
        "https://api.anthropic.com/v1/messages",
        {
          headers: headers(args.key),
          body: { model: args.model, max_tokens: args.maxTokens ?? 4096, system: args.system, messages: args.messages },
          signal: args.signal,
          timeoutMs: args.timeoutMs,
        },
        "anthropic",
        args.secrets,
      ),
    );
    const usage = asRecord(data.usage);
    const text = (Array.isArray(data.content) ? data.content : [])
      .map((block) => (asRecord(block).type === "text" ? String(asRecord(block).text ?? "") : ""))
      .join("");
    return {
      text,
      ...(asNumber(usage.input_tokens) !== undefined ? { inputTokens: asNumber(usage.input_tokens)! } : {}),
      ...(asNumber(usage.output_tokens) !== undefined ? { outputTokens: asNumber(usage.output_tokens)! } : {}),
    };
  },
  async list({ key, signal, secrets }: ListArgs): Promise<ModelInfo[]> {
    const data = asRecord(
      await providerRequest(
        "https://api.anthropic.com/v1/models?limit=100",
        { method: "GET", headers: headers(key), signal, timeoutMs: 12_000 },
        "anthropic",
        secrets,
      ),
    );
    return (Array.isArray(data.data) ? data.data : [])
      .map((entry) => asRecord(entry))
      .filter((m) => typeof m.id === "string" && m.id)
      .map((m) => {
        const context = asNumber(m.max_input_tokens);
        const output = asNumber(m.max_tokens);
        return {
          id: String(m.id),
          name: typeof m.display_name === "string" && m.display_name ? m.display_name : String(m.id),
          provider: "anthropic" as const,
          ...(context !== undefined ? { contextLength: context } : {}),
          ...(output !== undefined ? { maxOutput: output } : {}),
          tasks: ["chat completion"],
          compatible: true,
          recommended: false,
          source: "provider" as const,
          notes: [],
        };
      });
  },
};
