import { PROVIDERS, isProviderId } from "../shared/providers.js";
import { AppError } from "../server/errors.js";
import { handle, json, requestKeys } from "../server/http.js";
import { discoverModels } from "../server/providers/index.js";

export const GET = handle(async (req) => {
  const provider = new URL(req.url).searchParams.get("provider");
  if (!isProviderId(provider)) throw new AppError("invalid_input", { message: "Choose a provider." });
  const sent = requestKeys();
  const key = sent.provider === provider && sent.ai ? sent.ai : (process.env[PROVIDERS[provider].envVar]?.trim() ?? "");
  return json(await discoverModels(provider, key, req.signal), 200, { "cache-control": "no-store" });
});
