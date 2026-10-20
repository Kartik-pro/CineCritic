import { PROVIDER_IDS, isProviderId, type ProviderId } from "../shared/providers";

export interface Credentials {
  tmdb: string;
  provider: ProviderId;
  keys: Partial<Record<ProviderId, string>>;
  models: Partial<Record<ProviderId, string>>;
  remember: boolean;
}

export const EMPTY_CREDENTIALS: Credentials = { tmdb: "", provider: "gemini", keys: {}, models: {}, remember: false };

const SETTINGS = "cc.settings";
const SECRETS = "cc.secrets";
const LEGACY = "cc.keys";

type Store = Pick<Storage, "getItem" | "setItem" | "removeItem">;

function readJson(store: Store, key: string): Record<string, unknown> | null {
  try {
    const raw = store.getItem(key);
    const value: unknown = raw ? JSON.parse(raw) : null;
    return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function write(store: Store, key: string, value: unknown): void {
  try {
    store.setItem(key, JSON.stringify(value));
  } catch {
    return;
  }
}

function remove(store: Store, key: string): void {
  try {
    store.removeItem(key);
  } catch {
    return;
  }
}

const text = (value: unknown): string => (typeof value === "string" ? value.replace(/[^\x21-\x7e]/g, "") : "");

function perProvider(value: unknown): Partial<Record<ProviderId, string>> {
  const source = value && typeof value === "object" ? (value as Record<string, unknown>) : {};
  const out: Partial<Record<ProviderId, string>> = {};
  for (const id of PROVIDER_IDS) {
    const entry = text(source[id]);
    if (entry) out[id] = entry;
  }
  return out;
}

export function loadCredentials(): Credentials {
  const settings = readJson(localStorage, SETTINGS);
  const legacy = settings ? null : readJson(localStorage, LEGACY);
  if (legacy) {
    const provider = isProviderId(legacy.provider) ? legacy.provider : "gemini";
    const migrated: Credentials = {
      tmdb: text(legacy.tmdb),
      provider,
      keys: text(legacy.ai) ? { [provider]: text(legacy.ai) } : {},
      models: text(legacy.model) ? { [provider]: text(legacy.model) } : {},
      remember: true,
    };
    saveCredentials(migrated);
    remove(localStorage, LEGACY);
    return migrated;
  }
  if (!settings) return EMPTY_CREDENTIALS;
  const remember = settings.remember === true;
  const secrets = readJson(remember ? localStorage : sessionStorage, SECRETS) ?? readJson(sessionStorage, SECRETS);
  return {
    tmdb: text(secrets?.tmdb),
    provider: isProviderId(settings.provider) ? settings.provider : "gemini",
    keys: perProvider(secrets?.keys),
    models: perProvider(settings.models),
    remember,
  };
}

export function saveCredentials(credentials: Credentials): void {
  write(localStorage, SETTINGS, { provider: credentials.provider, models: credentials.models, remember: credentials.remember });
  const secrets = { tmdb: credentials.tmdb, keys: credentials.keys };
  const [target, other] = credentials.remember ? [localStorage, sessionStorage] : [sessionStorage, localStorage];
  write(target, SECRETS, secrets);
  remove(other, SECRETS);
}

export function clearCredentials(): void {
  remove(localStorage, SETTINGS);
  remove(localStorage, SECRETS);
  remove(localStorage, LEGACY);
  remove(sessionStorage, SECRETS);
}

export const activeKey = (credentials: Credentials): string => credentials.keys[credentials.provider] ?? "";
export const activeModel = (credentials: Credentials): string => credentials.models[credentials.provider] ?? "";

export function authHeaders(credentials: Credentials, options: { includeTmdb?: boolean } = {}): Record<string, string> {
  const headers: Record<string, string> = {};
  if (credentials.tmdb && options.includeTmdb !== false) headers["x-tmdb-key"] = credentials.tmdb;
  const key = activeKey(credentials);
  if (key) {
    headers["x-ai-key"] = key;
    headers["x-ai-provider"] = credentials.provider;
    const model = activeModel(credentials);
    if (model) headers["x-ai-model"] = model;
  }
  return headers;
}
