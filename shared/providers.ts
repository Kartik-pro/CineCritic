export const PROVIDER_IDS = ["gemini", "openai", "anthropic", "mistral", "huggingface"] as const;
export type ProviderId = (typeof PROVIDER_IDS)[number];

export const isProviderId = (value: unknown): value is ProviderId =>
  typeof value === "string" && (PROVIDER_IDS as readonly string[]).includes(value);

export interface ProviderMeta {
  id: ProviderId;
  label: string;
  tagline: string;
  envVar: string;
  keyHint: string;
  keyUrl: string;
  defaultModel: string;
  modelHint: string;
  notes: string[];
}

export const PROVIDERS: Record<ProviderId, ProviderMeta> = {
  gemini: {
    id: "gemini",
    label: "Google Gemini",
    tagline: "Google AI Studio",
    envVar: "GOOGLE_API_KEY",
    keyHint: "Google AI Studio key",
    keyUrl: "https://aistudio.google.com/apikey",
    defaultModel: "gemini-3.5-flash",
    modelHint: "gemini-3.5-flash",
    notes: [],
  },
  openai: {
    id: "openai",
    label: "OpenAI",
    tagline: "OpenAI API",
    envVar: "OPENAI_API_KEY",
    keyHint: "Starts with sk-",
    keyUrl: "https://platform.openai.com/api-keys",
    defaultModel: "gpt-4o-mini",
    modelHint: "gpt-4o-mini",
    notes: ["OpenAI's model list does not report capabilities, so compatibility is inferred from model names."],
  },
  anthropic: {
    id: "anthropic",
    label: "Anthropic",
    tagline: "Claude models",
    envVar: "ANTHROPIC_API_KEY",
    keyHint: "Starts with sk-ant-",
    keyUrl: "https://console.anthropic.com/settings/keys",
    defaultModel: "claude-sonnet-5-5",
    modelHint: "claude-sonnet-5-5",
    notes: [],
  },
  mistral: {
    id: "mistral",
    label: "Mistral",
    tagline: "Mistral AI",
    envVar: "MISTRAL_API_KEY",
    keyHint: "Mistral console key",
    keyUrl: "https://console.mistral.ai/api-keys",
    defaultModel: "mistral-large-latest",
    modelHint: "mistral-large-latest",
    notes: [],
  },
  huggingface: {
    id: "huggingface",
    label: "Hugging Face",
    tagline: "Inference Providers",
    envVar: "HF_TOKEN",
    keyHint: "Fine-grained token starting with hf_",
    keyUrl: "https://huggingface.co/settings/tokens",
    defaultModel: "",
    modelHint: "org/model or org/model:cheapest",
    notes: [
      "Create a fine-grained token with the “Make calls to Inference Providers” permission.",
      "Only models served by an inference provider work here. Models that need their own deployment are not supported.",
      "Append :fastest, :cheapest or a provider name to a model ID to choose routing, for example org/model:cheapest.",
      "Availability, pricing, quotas and latency vary by model and provider. See Hugging Face's pricing page for current terms.",
    ],
  },
};

export interface InferenceProviderInfo {
  name: string;
  status: string;
  contextLength?: number;
  supportsTools?: boolean;
  supportsStructuredOutput?: boolean;
}

export interface ModelInfo {
  id: string;
  name: string;
  provider: ProviderId;
  description?: string;
  contextLength?: number;
  maxOutput?: number;
  tasks: string[];
  compatible: boolean | null;
  recommended: boolean;
  source: "provider" | "default";
  inferenceProviders?: InferenceProviderInfo[];
  notes: string[];
}

export interface ModelCatalogue {
  provider: ProviderId;
  models: ModelInfo[];
  fetchedAt: number;
  source: "provider" | "default";
  warning?: string;
}

export const MODEL_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,199}$/;
