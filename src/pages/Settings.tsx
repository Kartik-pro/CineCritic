import { useState, type FormEvent } from "react";
import { PROVIDER_IDS, PROVIDERS, type ProviderId } from "../../shared/providers";
import { ModelPicker } from "../components/ModelPicker";
import { RunPanel, seconds } from "../components/Pipeline";
import { activeKey, activeModel, clearCredentials, EMPTY_CREDENTIALS, type Credentials } from "../keys";
import { operations } from "../pipeline/operations";
import { useRunner } from "../pipeline/useRunner";
import { useApp } from "../state";
import type { ConnectionResult } from "../../shared/types";

const clean = (value: string) => value.replace(/[^\x21-\x7e]/g, "");

interface Tested {
  signature: string;
  result: ConnectionResult;
}

export function Settings() {
  const { creds, setCreds, available, go } = useApp();
  const [draft, setDraft] = useState<Credentials>(creds);
  const [visible, setVisible] = useState(false);
  const [saved, setSaved] = useState(false);
  const [tested, setTested] = useState<Tested | null>(null);
  const runner = useRunner();
  const provider = PROVIDERS[draft.provider];
  const key = activeKey(draft);
  const model = activeModel(draft);
  const effectiveModel = model || provider.defaultModel;
  const signature = `${draft.provider}|${effectiveModel}|${key}`;
  const freshTest = tested && tested.signature === signature ? tested.result : null;
  const ready = !!available?.tmdb && !!available.ai;
  const type = visible ? "text" : "password";

  const edit = (patch: Partial<Credentials>) => {
    setDraft((prev) => ({ ...prev, ...patch }));
    setSaved(false);
  };
  const setKey = (value: string) => edit({ keys: { ...draft.keys, [draft.provider]: value } });
  const setModel = (value: string) => edit({ models: { ...draft.models, [draft.provider]: value } });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const keys = Object.fromEntries(PROVIDER_IDS.map((id) => [id, clean(draft.keys[id] ?? "")]).filter(([, v]) => v));
    const models = { ...draft.models, ...(effectiveModel ? { [draft.provider]: effectiveModel } : {}) };
    const next: Credentials = { ...draft, tmdb: clean(draft.tmdb), keys, models };
    setDraft(next);
    setCreds(next);
    setSaved(true);
  };

  const clear = () => {
    clearCredentials();
    setDraft(EMPTY_CREDENTIALS);
    setCreds(EMPTY_CREDENTIALS);
    setSaved(false);
    setTested(null);
    runner.reset();
  };

  const test = async () => {
    const snapshot = signature;
    const result = await runner.start(operations.connection({ ...draft, keys: { ...draft.keys, [draft.provider]: clean(key) }, models: { ...draft.models, [draft.provider]: effectiveModel } }));
    if (result) setTested({ signature: snapshot, result });
  };

  const canTest = !!key && !!effectiveModel && !runner.busy;

  return (
    <form className="panel settings" onSubmit={submit}>
      <div>
        <p className="eyebrow">Settings</p>
        <h2>Providers and keys</h2>
        <p className="muted">Choose how CineCritic talks to film data and to an AI model. Nothing changes until you press Save.</p>
      </div>

      <fieldset>
        <legend>Film data</legend>
        <label>
          TMDB API key
          <input type={type} value={draft.tmdb} onChange={(e) => edit({ tmdb: e.target.value })} placeholder="TMDB v3 key or v4 read token" autoComplete="off" spellCheck={false} />
        </label>
        <a href="https://www.themoviedb.org/settings/api" target="_blank" rel="noopener noreferrer">
          Get a free TMDB key
        </a>
      </fieldset>

      <fieldset>
        <legend>AI provider</legend>
        <div className="provider-grid" role="radiogroup" aria-label="AI provider">
          {PROVIDER_IDS.map((id: ProviderId) => (
            <label key={id} className={draft.provider === id ? "provider on" : "provider"}>
              <input type="radio" name="provider" value={id} checked={draft.provider === id} onChange={() => edit({ provider: id })} />
              <span className="provider-name">{PROVIDERS[id].label}</span>
              <span className="muted small">{PROVIDERS[id].tagline}</span>
              {creds.provider === id && <span className="badge good">Saved</span>}
            </label>
          ))}
        </div>
        <label>
          {provider.label} API key
          <input type={type} value={key} onChange={(e) => setKey(e.target.value)} placeholder={provider.keyHint} autoComplete="off" spellCheck={false} />
        </label>
        <a href={provider.keyUrl} target="_blank" rel="noopener noreferrer">
          Get a {provider.label} key
        </a>
        <label className="check">
          <input type="checkbox" checked={visible} onChange={(e) => setVisible(e.target.checked)} />
          Show keys
        </label>
      </fieldset>

      <fieldset>
        <legend>Model</legend>
        <ModelPicker draft={draft} value={effectiveModel} saved={creds.models[draft.provider] ?? ""} onChange={setModel} />
      </fieldset>

      <fieldset>
        <legend>Test connection</legend>
        <p className="muted small">Sends one short message with the selected key and model. It uses a small amount of your provider quota.</p>
        <div className="row">
          <button className="ghost" type="button" disabled={!canTest} onClick={() => void test()}>
            {runner.busy ? "Testing…" : "Test connection"}
          </button>
          {!key && <span className="muted small">Enter a key first.</span>}
          {key && !effectiveModel && <span className="muted small">Choose a model first.</span>}
        </div>
        <RunPanel run={runner.run} onCancel={runner.cancel} onRetry={() => void test()} />
        {freshTest && (
          <p className="notice">
            Connected to {freshTest.model} in {seconds(freshTest.latencyMs)}.{" "}
            {freshTest.modelListed === false ? "The provider did not list this model, but it responded. " : ""}
            {freshTest.inputTokens !== undefined && freshTest.outputTokens !== undefined ? `Test used ${freshTest.inputTokens} input and ${freshTest.outputTokens} output tokens. ` : ""}
            This confirms access now; it does not guarantee future quota or availability.
          </p>
        )}
        {tested && !freshTest && <p className="muted small">Settings changed since the last test. Test again to confirm.</p>}
      </fieldset>

      <fieldset>
        <legend>How your keys are stored</legend>
        <label className="check">
          <input type="checkbox" checked={draft.remember} onChange={(e) => edit({ remember: e.target.checked })} />
          Remember keys on this device
        </label>
        <ul className="notes small muted">
          <li>{draft.remember ? "Keys are kept in this browser's local storage until you clear them." : "Keys are kept only for this browser tab session and disappear when it closes."}</li>
          <li>Browser storage is not encrypted. Scripts or extensions running on this site, or anyone using this device, could read it.</li>
          <li>Each request sends your keys to this site's server over HTTPS so it can call TMDB and your provider. The server does not store or log them.</li>
          <li>Prefer restricted keys with spending limits, and avoid saving keys on shared computers.</li>
        </ul>
      </fieldset>

      {saved && <p className="notice" role="status">{ready ? "Saved. You're ready to analyze films." : "Saved. Add both a TMDB key and an AI key to continue."}</p>}

      <div className="row">
        <button className="primary" type="submit">
          Save settings
        </button>
        {saved && ready && (
          <button className="ghost" type="button" onClick={() => go("critique")}>
            Start analyzing
          </button>
        )}
        <button className="ghost danger" type="button" onClick={clear}>
          Clear all keys
        </button>
      </div>
    </form>
  );
}
