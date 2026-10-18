import { AsyncLocalStorage } from "node:async_hooks";

export interface RequestKeys {
  tmdb: string;
  provider: string;
  ai: string;
  model: string;
}

const EMPTY: RequestKeys = { tmdb: "", provider: "", ai: "", model: "" };
const store = new AsyncLocalStorage<RequestKeys>();

const header = (req: Request, name: string) => (req.headers.get(name) ?? "").trim().slice(0, 300);

export function readKeys(req: Request): RequestKeys {
  return {
    tmdb: header(req, "x-tmdb-key"),
    provider: header(req, "x-ai-provider").toLowerCase(),
    ai: header(req, "x-ai-key"),
    model: header(req, "x-ai-model"),
  };
}

export const withKeys = <T>(keys: RequestKeys, fn: () => T): T => store.run(keys, fn);

export const requestKeys = (): RequestKeys => store.getStore() ?? EMPTY;
