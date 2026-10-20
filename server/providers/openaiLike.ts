import type { InferenceProviderInfo, ModelInfo, ProviderId } from "../../shared/providers.js";
import { asNumber, asRecord, providerRequest } from "./request.js";
import type { GenerateArgs, GenerateResult, ListArgs, ProviderAdapter } from "./types.js";

const NON_CHAT_HINTS = ["embed", "whisper", "tts", "dall-e", "moderation", "davinci", "babbage", "transcribe", "image", "audio", "realtime", "search-preview"];

function contentText(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((part) => (typeof part === "string" ? part : typeof asRecord(part).text === "string" ? asRecord(part).text : ""))
      .join("");
  }
  return "";
}

async function chat(
  provider: ProviderId,
  baseUrl: string,
  args: GenerateArgs,
  jsonMode: boolean,
): Promise<GenerateResult> {
  const data = asRecord(
    await providerRequest(
      `${baseUrl}/chat/completions`,
      {
        headers: { authorization: `Bearer ${args.key}` },
        body: {
          model: args.model,
          messages: [{ role: "system", content: args.system }, ...args.messages],
          ...(args.json && jsonMode ? { response_format: { type: "json_object" } } : {}),
        },
        signal: args.signal,
        timeoutMs: args.timeoutMs,
      },
      provider,
      args.secrets,
    ),
  );
  const usage = asRecord(data.usage);
  return {
    text: contentText(asRecord(asRecord(data.choices?.[0]).message).content),
    ...(asNumber(usage.prompt_tokens) !== undefined ? { inputTokens: asNumber(usage.prompt_tokens)! } : {}),
    ...(asNumber(usage.completion_tokens) !== undefined ? { outputTokens: asNumber(usage.completion_tokens)! } : {}),
  };
}

const model = (provider: ProviderId, id: string, extra: Partial<ModelInfo> = {}): ModelInfo => ({
  id,
  name: id,
  provider,
  tasks: [],
  compatible: null,
  recommended: false,
  source: "provider",
  notes: [],
  ...extra,
});

export const openai: ProviderAdapter = {
  needsKeyToList: true,
  generate: (args) => chat("openai", "https://api.openai.com/v1", args, true),
  async list({ key, signal, secrets }: ListArgs) {
    const data = asRecord(
      await providerRequest(
        "https://api.openai.com/v1/models",
        { method: "GET", headers: { authorization: `Bearer ${key}` }, signal, timeoutMs: 12_000 },
        "openai",
        secrets,
      ),
    );
    return (Array.isArray(data.data) ? data.data : [])
      .map((m) => String(asRecord(m).id ?? ""))
      .filter(Boolean)
      .map((id) => {
        const nonChat = NON_CHAT_HINTS.some((hint) => id.toLowerCase().includes(hint));
        return model("openai", id, {
          compatible: nonChat ? false : null,
          notes: nonChat
            ? ["Name suggests this is not a text-generation model."]
            : ["OpenAI does not report capabilities. Use Test connection to verify this model."],
        });
      });
  },
};

export const mistral: ProviderAdapter = {
  needsKeyToList: true,
  generate: (args) => chat("mistral", "https://api.mistral.ai/v1", args, true),
  async list({ key, signal, secrets }: ListArgs) {
    const data = asRecord(
      await providerRequest(
        "https://api.mistral.ai/v1/models",
        { method: "GET", headers: { authorization: `Bearer ${key}` }, signal, timeoutMs: 12_000 },
        "mistral",
        secrets,
      ),
    );
    return (Array.isArray(data.data) ? data.data : [])
      .map((entry) => asRecord(entry))
      .filter((m) => m.id)
      .map((m) => {
        const caps = asRecord(m.capabilities);
        const chatCapable = typeof caps.completion_chat === "boolean" ? caps.completion_chat : null;
        const context = asNumber(m.max_context_length);
        return model("mistral", String(m.id), {
          name: typeof m.name === "string" && m.name ? m.name : String(m.id),
          ...(typeof m.description === "string" && m.description ? { description: m.description } : {}),
          ...(context !== undefined ? { contextLength: context } : {}),
          tasks: chatCapable ? ["chat completion"] : [],
          compatible: chatCapable,
        });
      });
  },
};

export const huggingface: ProviderAdapter = {
  needsKeyToList: false,
  generate: (args) => chat("huggingface", "https://router.huggingface.co/v1", args, false),
  async list({ signal, secrets }: ListArgs) {
    const data = asRecord(
      await providerRequest(
        "https://router.huggingface.co/v1/models",
        { method: "GET", signal, timeoutMs: 15_000 },
        "huggingface",
        secrets,
      ),
    );
    return (Array.isArray(data.data) ? data.data : [])
      .map((entry) => asRecord(entry))
      .filter((m) => typeof m.id === "string" && m.id)
      .map((m) => {
        const providers: InferenceProviderInfo[] = (Array.isArray(m.providers) ? m.providers : [])
          .map((p) => asRecord(p))
          .filter((p) => typeof p.provider === "string")
          .map((p) => {
            const context = asNumber(p.context_length);
            return {
              name: String(p.provider),
              status: typeof p.status === "string" ? p.status : "unknown",
              ...(context !== undefined ? { contextLength: context } : {}),
              ...(typeof p.supports_tools === "boolean" ? { supportsTools: p.supports_tools } : {}),
              ...(typeof p.supports_structured_output === "boolean" ? { supportsStructuredOutput: p.supports_structured_output } : {}),
            };
          });
        const live = providers.filter((p) => p.status === "live");
        const contexts = providers.map((p) => p.contextLength ?? 0);
        const best = Math.max(0, ...contexts);
        return model("huggingface", String(m.id), {
          ...(typeof m.owned_by === "string" && m.owned_by ? { description: `Published by ${m.owned_by}` } : {}),
          ...(best > 0 ? { contextLength: best } : {}),
          tasks: ["chat completion (router)"],
          compatible: providers.length ? live.length > 0 : null,
          recommended: live.some((p) => p.supportsStructuredOutput === true),
          inferenceProviders: providers,
          notes: providers.length
            ? live.length
              ? []
              : ["No inference provider currently reports this model as live."]
            : ["Hugging Face did not report provider details for this model."],
        });
      })
      .sort((a, b) => Number(b.recommended) - Number(a.recommended) || a.id.localeCompare(b.id));
  },
};
