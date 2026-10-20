import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { authHeaders, clearCredentials, EMPTY_CREDENTIALS, loadCredentials, saveCredentials } from "../src/keys";

const store = () => {
  const m = new Map<string, string>();
  return { m, getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), removeItem: (k: string) => void m.delete(k) };
};
let local = store();
let session = store();

beforeEach(() => {
  local = store();
  session = store();
  (globalThis as any).localStorage = local;
  (globalThis as any).sessionStorage = session;
});

test("keys stay in the tab session unless remember is on", () => {
  saveCredentials({ ...EMPTY_CREDENTIALS, tmdb: "t", provider: "openai", keys: { openai: "sk-1" }, models: { openai: "gpt-x" }, remember: false });
  assert.ok(session.m.has("cc.secrets"));
  assert.ok(!local.m.has("cc.secrets"));
  assert.ok(!local.m.get("cc.settings")!.includes("sk-1"));
  assert.equal(loadCredentials().keys.openai, "sk-1");
  saveCredentials({ ...EMPTY_CREDENTIALS, tmdb: "t", provider: "openai", keys: { openai: "sk-1" }, remember: true });
  assert.ok(local.m.has("cc.secrets"));
  assert.ok(!session.m.has("cc.secrets"));
});

test("older saved keys are migrated and kept on the device", () => {
  local.setItem("cc.keys", JSON.stringify({ tmdb: "t", provider: "anthropic", ai: "sk-ant", model: "m" }));
  const loaded = loadCredentials();
  assert.equal(loaded.provider, "anthropic");
  assert.equal(loaded.keys.anthropic, "sk-ant");
  assert.equal(loaded.models.anthropic, "m");
  assert.equal(loaded.remember, true);
  assert.ok(!local.m.has("cc.keys"));
  assert.equal(loadCredentials().keys.anthropic, "sk-ant");
});

test("each provider keeps its own key and headers use the active one", () => {
  const creds = { ...EMPTY_CREDENTIALS, provider: "huggingface" as const, keys: { openai: "sk-1", huggingface: "hf_abc" }, models: { huggingface: "org/m" } };
  assert.deepEqual(authHeaders(creds), { "x-ai-key": "hf_abc", "x-ai-provider": "huggingface", "x-ai-model": "org/m" });
  assert.deepEqual(authHeaders({ ...creds, tmdb: "t" }, { includeTmdb: false }), { "x-ai-key": "hf_abc", "x-ai-provider": "huggingface", "x-ai-model": "org/m" });
});

test("clearing removes every stored secret and tolerates blocked storage", () => {
  saveCredentials({ ...EMPTY_CREDENTIALS, keys: { gemini: "g" }, remember: true });
  clearCredentials();
  assert.equal(local.m.size + session.m.size, 0);
  (globalThis as any).localStorage = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); }, removeItem() { throw new Error("blocked"); } };
  assert.deepEqual(loadCredentials(), EMPTY_CREDENTIALS);
  assert.doesNotThrow(() => saveCredentials(EMPTY_CREDENTIALS));
});
