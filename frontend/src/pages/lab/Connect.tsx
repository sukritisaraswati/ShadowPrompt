/**
 * LLM connection: choose a provider, enter credentials, run the benign probe.
 *
 * SECURITY: the API key is typed into a password field, kept in React state
 * only (see SessionContext), and sent to our own backend over HTTPS. It is
 * never placed in the URL, storage, or the console.
 */

import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { toApiError } from "@/api/client";
import { getCapabilities, PROVIDER_LABELS, PROVIDER_PRESETS, testConnection } from "@/api/lab";
import type { ApiError, ConnectionTestResult, LabCapabilities, LlmProvider } from "@/api/types";
import ErrorAlert from "@/components/ErrorAlert";
import ChatbotConnect from "@/pages/lab/ChatbotConnect";
import { describeConnection, useSession, type LlmConnection } from "@/context/SessionContext";

const INPUT =
  "mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-accent-500 focus:outline-none focus:ring-2 focus:ring-accent-400 dark:border-slate-700 dark:bg-shadow-900";

export default function Connect() {
  const session = useSession();
  const [presetId, setPresetId] = useState("openai");
  const preset = PROVIDER_PRESETS.find((p) => p.id === presetId) ?? PROVIDER_PRESETS[0];
  const [provider, setProvider] = useState<LlmProvider>(preset.provider);
  const [baseUrl, setBaseUrl] = useState(preset.baseUrl);
  const [model, setModel] = useState(preset.model);
  const [apiKey, setApiKey] = useState("");
  const [validation, setValidation] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<ConnectionTestResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [target, setTarget] = useState<"model" | "chatbot">(
    session.connection?.provider === "chatbot" ? "chatbot" : "model",
  );
  const [capabilities, setCapabilities] = useState<LabCapabilities | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    // Only used to explain local presets; the backend enforces the rule anyway.
    getCapabilities(controller.signal)
      .then(setCapabilities)
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  const localBlocked = Boolean(preset.local && capabilities && !capabilities.local_endpoints_allowed);

  function choosePreset(id: string) {
    const next = PROVIDER_PRESETS.find((p) => p.id === id);
    if (!next) return;
    setPresetId(id);
    setProvider(next.provider);
    setBaseUrl(next.baseUrl);
    setModel(next.model);
    setResult(null);
    setError(null);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setResult(null);

    let problem: string | null = null;
    try {
      const url = new URL(baseUrl.trim());
      if (url.protocol !== "http:" && url.protocol !== "https:") problem = "The base URL must use http or https.";
    } catch {
      problem = "Enter the full base URL, for example https://api.openai.com/v1.";
    }
    if (!problem && !model.trim()) problem = "Enter the model name.";
    if (!problem && preset.needsKey && !apiKey.trim()) problem = "Enter your API key for this provider.";
    setValidation(problem);
    if (problem) return;

    const connection: LlmConnection = {
      provider,
      baseUrl: baseUrl.trim(),
      modelName: model.trim(),
      apiKey: apiKey.trim() || undefined,
    };
    session.setConnection(connection);
    setBusy(true);
    try {
      const outcome = await testConnection(connection);
      session.setVerifiedConnection(connection, outcome.session_id);
      setResult(outcome);
      // The form no longer needs its own copy of the key.
      setApiKey("");
    } catch (cause) {
      setError(toApiError(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="max-w-2xl">
      <h1 className="text-2xl font-bold tracking-tight">Connect a target</h1>
      <p className="mt-2 text-slate-600 dark:text-slate-300">
        Connect what you want to test. A single harmless message checks the connection
        before any attack is sent.
      </p>

      <div role="radiogroup" aria-label="What are you testing?" className="mt-5 grid gap-3 sm:grid-cols-2">
        {(
          [
            ["model", "A model API", "OpenAI, Anthropic, Gemini, Azure, or a local model. Tests bring their own instructions."],
            ["chatbot", "My chatbot", "Your own bot's endpoint, with its own instructions, data and filters."],
          ] as const
        ).map(([value, label, help]) => (
          <label
            key={value}
            className={`cursor-pointer rounded-lg border p-3 text-sm ${
              target === value ? "border-accent-500 bg-accent-500/5" : "border-slate-200 dark:border-slate-800"
            }`}
          >
            <input type="radio" name="target" className="sr-only" checked={target === value} onChange={() => setTarget(value)} />
            <span className="font-semibold">{label}</span>
            <span className="mt-1 block text-xs text-slate-500">{help}</span>
          </label>
        ))}
      </div>

      {session.isVerified && session.connection && !result && (
        <div className="mt-4 flex flex-wrap items-center gap-3 rounded-md border border-emerald-300 bg-emerald-50 px-4 py-3 text-sm text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-100">
          <span>Connected: {describeConnection(session.connection)}</span>
          <Link to="/lab/configure" className="font-medium underline">
            Set up a campaign
          </Link>
          <button type="button" onClick={session.clearSession} className="ml-auto underline">
            Disconnect
          </button>
        </div>
      )}

      {target === "chatbot" ? (
        <ChatbotConnect />
      ) : (
        <>
      <form onSubmit={onSubmit} noValidate className="mt-6 space-y-4">
        <div>
          <label htmlFor="preset" className="block text-sm font-medium">
            Provider
          </label>
          <select id="preset" value={presetId} onChange={(e) => choosePreset(e.target.value)} disabled={busy} className={INPUT}>
            <optgroup label="Hosted APIs">
              {PROVIDER_PRESETS.filter((p) => !p.local).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </optgroup>
            <optgroup label="Local models (self-hosted ShadowPrompt only)">
              {PROVIDER_PRESETS.filter((p) => p.local).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </optgroup>
          </select>
        </div>

        {preset.local && localBlocked && (
          <div role="note" className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100">
            This ShadowPrompt server does not allow local endpoints, because letting a shared server
            reach its own network would be a security hole. Run ShadowPrompt yourself and set{" "}
            <code className="font-mono">LLM_ALLOW_PRIVATE_ENDPOINTS=true</code> to test models on your own machine.
          </div>
        )}
        {preset.local && !localBlocked && (
          <div role="note" className="rounded-md border border-slate-200 px-4 py-3 text-sm text-slate-600 dark:border-slate-800 dark:text-slate-300">
            Start {preset.label} with its OpenAI-compatible server and load a model first. No API key is
            needed. If ShadowPrompt runs in Docker, replace <code className="font-mono">localhost</code> with{" "}
            <code className="font-mono">host.docker.internal</code>.
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="api-format" className="block text-sm font-medium">
              API format
            </label>
            <select id="api-format" value={provider} onChange={(e) => setProvider(e.target.value as LlmProvider)} disabled={busy} className={INPUT}>
              {Object.entries(PROVIDER_LABELS).filter(([value]) => value !== "chatbot").map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="model" className="block text-sm font-medium">
              Model name
            </label>
            <input id="model" value={model} onChange={(e) => setModel(e.target.value)} disabled={busy} autoComplete="off" spellCheck={false} className={INPUT} />
          </div>
        </div>

        <div>
          <label htmlFor="base-url" className="block text-sm font-medium">
            Base URL
          </label>
          <input id="base-url" type="url" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} disabled={busy} autoComplete="off" spellCheck={false} className={INPUT} />
        </div>

        <div>
          <label htmlFor="api-key" className="block text-sm font-medium">
            API key{preset.needsKey ? "" : " (optional)"}
          </label>
          <input
            id="api-key"
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            disabled={busy}
            autoComplete="off"
            spellCheck={false}
            aria-describedby="key-help"
            className={INPUT}
          />
          <p id="key-help" className="mt-1 text-xs text-slate-500">
            Held in this browser tab's memory only. It is never saved, logged, or shown again,
            and it disappears when you close or reload the tab.
          </p>
        </div>

        {validation && (
          <p role="alert" className="text-sm text-rose-700 dark:text-rose-400">
            {validation}
          </p>
        )}

        <button type="submit" disabled={busy || localBlocked} className="rounded-md bg-accent-500 px-4 py-2 text-sm font-medium text-white hover:bg-accent-600 disabled:opacity-60">
          {busy ? "Testing connection…" : "Test connection"}
        </button>
      </form>

      {error && (
        <div className="mt-6">
          <ErrorAlert error={error} title="The connection test failed." />
        </div>
      )}

      {result && (
        <div role="status" className="mt-6 rounded-md border border-emerald-300 bg-emerald-50 px-4 py-3 text-sm text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-100">
          <p className="font-semibold">Connected to {result.model_name}.</p>
          <p className="mt-1">
            {result.endpoint_host} answered in {result.latency_ms} ms. Reply: <span className="font-mono">{result.reply_preview || "(empty)"}</span>
          </p>
          <Link to="/lab/configure" className="mt-3 inline-block rounded-md bg-accent-500 px-3 py-1.5 font-medium text-white hover:bg-accent-600">
            Continue to campaign setup
          </Link>
        </div>
      )}
        </>
      )}
    </section>
  );
}
