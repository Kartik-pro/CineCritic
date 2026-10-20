import type { ModelInfo } from "../../shared/providers.js";
import { asNumber, asRecord, providerRequest } from "./request.js";
import type { GenerateArgs, GenerateResult, ListArgs, ProviderAdapter } from "./types.js";

export const gemini: ProviderAdapter = {
  needsKeyToList: true,
  async generate(args: GenerateArgs): Promise<GenerateResult> {
    const data = asRecord(
      await providerRequest(
        `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(args.model)}:generateContent`,
        {
          headers: { "x-goog-api-key": args.key },
          body: {
            systemInstruction: { parts: [{ text: args.system }] },
            contents: args.messages.map((m) => ({ role: m.role === "assistant" ? "model" : "user", parts: [{ text: m.content }] })),
            generationConfig: args.json ? { responseMimeType: "application/json" } : {},
          },
          signal: args.signal,
          timeoutMs: args.timeoutMs,
        },
        "gemini",
        args.secrets,
      ),
    );
    const parts: Record<string, any>[] = Array.isArray(data.candidates?.[0]?.content?.parts) ? data.candidates[0].content.parts : [];
    const usage = asRecord(data.usageMetadata);
    return {
      text: parts.filter((p) => !p.thought).map((p) => String(p.text ?? "")).join(""),
      ...(asNumber(usage.promptTokenCount) !== undefined ? { inputTokens: asNumber(usage.promptTokenCount)! } : {}),
      ...(asNumber(usage.candidatesTokenCount) !== undefined ? { outputTokens: asNumber(usage.candidatesTokenCount)! } : {}),
    };
  },
  async list({ key, signal, secrets }: ListArgs): Promise<ModelInfo[]> {
    const data = asRecord(
      await providerRequest(
        "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
        { method: "GET", headers: { "x-goog-api-key": key }, signal, timeoutMs: 12_000 },
        "gemini",
        secrets,
      ),
    );
    return (Array.isArray(data.models) ? data.models : [])
      .map((entry) => asRecord(entry))
      .filter((m) => typeof m.name === "string" && m.name)
      .map((m) => {
        const id = String(m.name).replace(/^models\//, "");
        const methods: string[] = Array.isArray(m.supportedGenerationMethods) ? m.supportedGenerationMethods.map(String) : [];
        const generates = methods.length ? methods.includes("generateContent") : null;
        const context = asNumber(m.inputTokenLimit);
        const output = asNumber(m.outputTokenLimit);
        return {
          id,
          name: typeof m.displayName === "string" && m.displayName ? m.displayName : id,
          provider: "gemini" as const,
          ...(typeof m.description === "string" && m.description ? { description: m.description } : {}),
          ...(context !== undefined ? { contextLength: context } : {}),
          ...(output !== undefined ? { maxOutput: output } : {}),
          tasks: methods,
          compatible: generates,
          recommended: false,
          source: "provider" as const,
          notes: generates === false ? ["This model does not support text generation."] : [],
        };
      });
  },
};
