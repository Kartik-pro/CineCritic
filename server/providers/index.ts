import { PROVIDERS, type ModelCatalogue, type ModelInfo, type ProviderId } from "../../shared/providers.js";
import { AppError } from "../errors.js";
import { anthropic } from "./anthropic.js";
import { gemini } from "./gemini.js";
import { huggingface, mistral, openai } from "./openaiLike.js";
import type { ProviderAdapter } from "./types.js";

export const ADAPTERS: Record<ProviderId, ProviderAdapter> = { gemini, openai, anthropic, mistral, huggingface };

function defaultEntry(provider: ProviderId): ModelInfo[] {
  const id = PROVIDERS[provider].defaultModel;
  if (!id) return [];
  return [
    {
      id,
      name: id,
      provider,
      tasks: [],
      compatible: null,
      recommended: true,
      source: "default",
      notes: ["CineCritic's suggested starting model. Use Test connection to verify it with your key."],
    },
  ];
}

export async function discoverModels(provider: ProviderId, key: string, signal: AbortSignal): Promise<ModelCatalogue> {
  const adapter = ADAPTERS[provider];
  const fallback = (warning: string): ModelCatalogue => ({
    provider,
    models: defaultEntry(provider),
    fetchedAt: Date.now(),
    source: "default",
    warning,
  });
  if (adapter.needsKeyToList && !key) {
    return fallback(`Add your ${PROVIDERS[provider].label} key to load its model list.`);
  }
  try {
    const listed = await adapter.list({ key, signal, secrets: [key] });
    if (!listed.length) return fallback("The provider returned no models for this key.");
    const defaultId = PROVIDERS[provider].defaultModel;
    const models = listed.map((m) => (m.id === defaultId ? { ...m, recommended: true } : m));
    return { provider, models, fetchedAt: Date.now(), source: "provider" };
  } catch (error) {
    const message = error instanceof AppError ? `${error.message} ${error.nextStep}` : "The model list could not be loaded.";
    return fallback(message);
  }
}
