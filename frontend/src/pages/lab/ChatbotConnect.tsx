/**
 * Connecting the user's own chatbot: its endpoint, how to call it, and the
 * canary that lets secret-leak tests run against it.
 *
 * SECURITY: header values (such as an Authorization token) are typed into
 * password fields, held in React state only (see SessionContext), and sent
 * only to our own backend. The response preview is untrusted text and is
 * rendered as text.
 */

import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { toApiError } from "@/api/client";
import { canarySnippet, generateCanary, TEMPLATES, testConnection, validateChatbot } from "@/api/lab";
import type { ApiError, ChatbotSettings, ConnectionTestResult, ConversationMode } from "@/api/types";
import ErrorAlert from "@/components/ErrorAlert";
import { useSession, type LlmConnection } from "@/context/SessionContext";

const INPUT =
  "mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-accent-500 focus:outline-none focus:ring-2 focus:ring-accent-400 dark:border-slate-700 dark:bg-shadow-900";

const MODES: { mode: ConversationMode; label: string; help: string }[] = [
  {
    mode: "history",
    label: "I send the history",
    help: "Your endpoint is stateless, so each request carries the earlier turns in {{history}}.",
  },
  {
    mode: "server",
    label: "My server keeps the conversation",
    help: "Your endpoint remembers turns under {{conversation_id}}; each request carries one new message.",
  },
  {
    mode: "message",
    label: "Single messages only",
    help: "No memory at all. Multi-turn tests (D4, D5 conversations, I5) are skipped.",
  },
];

export default function ChatbotConnect() {
  const session = useSession();
  const [name, setName] = useState("My chatbot");
  const [url, setUrl] = useState("");
  const [mode, setMode] = useState<ConversationMode>("history");
  const [template, setTemplate] = useState(TEMPLATES.history);
  const [responsePath, setResponsePath] = useState("reply");
  const [headers, setHeaders] = useState([{ name: "Authorization", value: "" }]);
  const [canary, setCanary] = useState(generateCanary);
  const [planted, setPlanted] = useState(false);
  const [copied, setCopied] = useState(false);
  const [validation, setValidation] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<ConnectionTestResult | null>(null);
  const [busy, setBusy] = useState(false);

  function chooseMode(next: ConversationMode) {
    // Swap the template only if it is still one of the starting points.
    if (Object.values(TEMPLATES).includes(template)) setTemplate(TEMPLATES[next]);
    setMode(next);
  }

  function setHeader(index: number, field: "name" | "value", value: string) {
    setHeaders((current) => current.map((h, i) => (i === index ? { ...h, [field]: value } : h)));
  }

  async function copySnippet() {
    try {
      await navigator.clipboard.writeText(canarySnippet(canary));
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setResult(null);
    const settings: ChatbotSettings = {
      bodyTemplate: template,
      responsePath: responsePath.trim(),
      mode,
      headers: headers.filter((h) => h.name.trim() && h.value),
      canary: planted ? canary : undefined,
    };
    let problem: string | null = null;
    try {
      const parsed = new URL(url.trim());
      if (parsed.protocol !== "http:" && parsed.protocol !== "https:") problem = "The endpoint must use http or https.";
    } catch {
      problem = "Enter the full endpoint URL, for example https://bot.example.com/api/chat.";
    }
    if (!problem && !name.trim()) problem = "Give your chatbot a name.";
    problem = problem ?? validateChatbot(settings);
    setValidation(problem);
    if (problem) return;

    const connection: LlmConnection = {
      provider: "chatbot",
      baseUrl: url.trim(),
      modelName: name.trim(),
      chatbot: settings,
    };
    session.setConnection(connection);
    setBusy(true);
    try {
      const outcome = await testConnection(connection);
      session.setVerifiedConnection(connection, outcome.session_id);
      setResult(outcome);
      // The form no longer needs its own copy of the credentials.
      setHeaders((current) => current.map((h) => ({ ...h, value: "" })));
    } catch (cause) {
      setError(toApiError(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <form onSubmit={onSubmit} noValidate className="mt-6 space-y-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="bot-name" className="block text-sm font-medium">
              Chatbot name
            </label>
            <input id="bot-name" value={name} onChange={(e) => setName(e.target.value)} disabled={busy} className={INPUT} />
          </div>
          <div>
            <label htmlFor="bot-url" className="block text-sm font-medium">
              Chat endpoint URL
            </label>
            <input
              id="bot-url"
              type="url"
              placeholder="https://bot.example.com/api/chat"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              disabled={busy}
              autoComplete="off"
              spellCheck={false}
              className={INPUT}
            />
          </div>
        </div>

        <fieldset>
          <legend className="text-sm font-medium">How does your chatbot handle a conversation?</legend>
          <div className="mt-2 space-y-2">
            {MODES.map((m) => (
              <label key={m.mode} className="flex items-start gap-2 text-sm">
                <input type="radio" name="mode" checked={mode === m.mode} onChange={() => chooseMode(m.mode)} disabled={busy} className="mt-1" />
                <span>
                  {m.label}
                  <span className="block text-xs text-slate-500">{m.help}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <div>
          <label htmlFor="bot-template" className="block text-sm font-medium">
            Request body (JSON)
          </label>
          <p className="text-xs text-slate-500">
            Placeholders: <code>{"{{message}}"}</code>, <code>{"{{history}}"}</code>, <code>{"{{messages}}"}</code>,{" "}
            <code>{"{{conversation_id}}"}</code>. Keep them in quotes; lists are filled in as JSON arrays.
          </p>
          <textarea
            id="bot-template"
            rows={6}
            value={template}
            onChange={(e) => setTemplate(e.target.value)}
            disabled={busy}
            spellCheck={false}
            className={`${INPUT} font-mono`}
          />
        </div>

        <div>
          <label htmlFor="bot-path" className="block text-sm font-medium">
            Where the reply is in the response
          </label>
          <input
            id="bot-path"
            value={responsePath}
            onChange={(e) => setResponsePath(e.target.value)}
            disabled={busy}
            placeholder="reply   or   data.choices.0.text   (empty: the whole body)"
            spellCheck={false}
            className={`${INPUT} font-mono`}
          />
        </div>

        <fieldset>
          <legend className="text-sm font-medium">Headers</legend>
          <p className="text-xs text-slate-500">
            For example an Authorization token. Values are held in this tab's memory only and are never stored.
          </p>
          <div className="mt-2 space-y-2">
            {headers.map((header, index) => (
              <div key={index} className="flex gap-2">
                <input
                  aria-label={`Header ${index + 1} name`}
                  value={header.name}
                  onChange={(e) => setHeader(index, "name", e.target.value)}
                  disabled={busy}
                  spellCheck={false}
                  className={`${INPUT} mt-0 w-48`}
                />
                <input
                  aria-label={`Header ${index + 1} value`}
                  type="password"
                  value={header.value}
                  onChange={(e) => setHeader(index, "value", e.target.value)}
                  disabled={busy}
                  autoComplete="off"
                  className={`${INPUT} mt-0`}
                />
                <button
                  type="button"
                  onClick={() => setHeaders((current) => current.filter((_, i) => i !== index))}
                  disabled={busy}
                  className="text-sm text-slate-500 hover:underline"
                >
                  Remove
                </button>
              </div>
            ))}
            {headers.length < 10 && (
              <button
                type="button"
                onClick={() => setHeaders((current) => [...current, { name: "", value: "" }])}
                disabled={busy}
                className="text-sm text-accent-500 hover:underline"
              >
                Add a header
              </button>
            )}
          </div>
        </fieldset>

        <fieldset className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
          <legend className="px-1 text-sm font-medium">Canary for secret-leak tests</legend>
          <p className="text-sm text-slate-600 dark:text-slate-300">
            Many tests try to make the bot reveal something it guards. Add this line to your chatbot's instructions (its
            system prompt) for the test run. It is made up, so leaking it harms nothing, and it lets us prove a leak
            beyond doubt.
          </p>
          <pre className="evidence mt-2" data-testid="canary-snippet">
            {canarySnippet(canary)}
          </pre>
          <div className="mt-2 flex flex-wrap gap-3 text-sm">
            <button type="button" onClick={copySnippet} className="text-accent-500 hover:underline">
              {copied ? "Copied" : "Copy"}
            </button>
            <button
              type="button"
              onClick={() => {
                setCanary(generateCanary());
                setCopied(false);
              }}
              disabled={busy}
              className="text-accent-500 hover:underline"
            >
              New canary
            </button>
          </div>
          <label className="mt-3 flex items-start gap-2 text-sm">
            <input type="checkbox" checked={planted} onChange={(e) => setPlanted(e.target.checked)} disabled={busy} className="mt-1" />
            <span>
              I've added it to my chatbot's instructions.
              <span className="block text-xs text-slate-500">
                Without it, tests that need a guarded secret are skipped; the rest still run.
              </span>
            </span>
          </label>
        </fieldset>

        {validation && (
          <p role="alert" className="text-sm text-rose-700 dark:text-rose-400">
            {validation}
          </p>
        )}

        <button type="submit" disabled={busy} className="rounded-md bg-accent-500 px-4 py-2 text-sm font-medium text-white hover:bg-accent-600 disabled:opacity-60">
          {busy ? "Testing connection…" : "Test connection"}
        </button>
      </form>

      {error && (
        <div className="mt-6">
          <ErrorAlert error={error} title="The chatbot could not be reached." />
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
  );
}
