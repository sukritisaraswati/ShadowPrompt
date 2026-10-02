/**
 * ShadowScan input: scan a public URL or an uploaded HTML file.
 */

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { toApiError } from "@/api/client";
import { scanFile, scanUrl, validateScanFile, validateScanUrl } from "@/api/scan";
import type { ApiError } from "@/api/types";
import ErrorAlert from "@/components/ErrorAlert";

type Mode = "url" | "file";

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: string;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
        active
          ? "bg-accent-500 text-white"
          : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-shadow-800"
      }`}
    >
      {children}
    </button>
  );
}

export default function Scanner() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>("url");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [validation, setValidation] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);

  // Abandon an in-flight scan if the user navigates away.
  useEffect(() => () => controller.current?.abort(), []);

  function switchMode(next: Mode) {
    setMode(next);
    setValidation(null);
    setError(null);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    const problem =
      mode === "url" ? validateScanUrl(url) : file ? validateScanFile(file) : "Choose a file to scan.";
    setValidation(problem);
    if (problem) return;

    controller.current = new AbortController();
    setBusy(true);
    try {
      const result =
        mode === "url"
          ? await scanUrl(url.trim(), controller.current.signal)
          : await scanFile(file as File, controller.current.signal);
      navigate(`/scan/results/${result.id}`);
    } catch (cause) {
      if (!controller.current?.signal.aborted) setError(toApiError(cause));
    } finally {
      setBusy(false);
      controller.current = null;
    }
  }

  function cancel() {
    controller.current?.abort();
    setBusy(false);
  }

  return (
    <section className="max-w-2xl">
      <h1 className="text-2xl font-bold tracking-tight">ShadowScan</h1>
      <p className="mt-2 text-slate-600 dark:text-slate-300">
        Find content in a webpage that could manipulate an AI model reading it. The page is
        parsed as static text and never executed.
      </p>

      <div role="tablist" aria-label="Scan source" className="mt-6 flex gap-2">
        <TabButton active={mode === "url"} onClick={() => switchMode("url")}>
          Scan a URL
        </TabButton>
        <TabButton active={mode === "file"} onClick={() => switchMode("file")}>
          Upload HTML
        </TabButton>
      </div>

      <form onSubmit={onSubmit} noValidate className="mt-4 space-y-4">
        {mode === "url" ? (
          <div>
            <label htmlFor="scan-url" className="block text-sm font-medium">
              Page URL
            </label>
            <input
              id="scan-url"
              type="url"
              inputMode="url"
              autoComplete="off"
              spellCheck={false}
              placeholder="https://example.com/article"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              disabled={busy}
              aria-invalid={Boolean(validation)}
              aria-describedby={validation ? "scan-validation" : "url-help"}
              className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-accent-500 focus:outline-none focus:ring-2 focus:ring-accent-400 dark:border-slate-700 dark:bg-shadow-900"
            />
            <p id="url-help" className="mt-1 text-xs text-slate-500">
              Public http and https pages only. Private and internal addresses are refused.
            </p>
          </div>
        ) : (
          <div>
            <label htmlFor="scan-file" className="block text-sm font-medium">
              HTML file
            </label>
            <input
              id="scan-file"
              type="file"
              accept=".html,.htm,text/html"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              disabled={busy}
              aria-invalid={Boolean(validation)}
              aria-describedby={validation ? "scan-validation" : "file-help"}
              className="mt-1 block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-2 file:text-sm dark:file:bg-shadow-800 dark:file:text-slate-200"
            />
            <p id="file-help" className="mt-1 text-xs text-slate-500">
              .html or .htm, up to 2 MB.
            </p>
          </div>
        )}

        {validation && (
          <p id="scan-validation" role="alert" className="text-sm text-rose-700 dark:text-rose-400">
            {validation}
          </p>
        )}

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={busy}
            className="rounded-md bg-accent-500 px-4 py-2 text-sm font-medium text-white hover:bg-accent-600 disabled:opacity-60"
          >
            {busy ? "Scanning…" : "Start scan"}
          </button>
          {busy && (
            <button
              type="button"
              onClick={cancel}
              className="rounded-md border border-slate-300 px-4 py-2 text-sm dark:border-slate-700"
            >
              Cancel
            </button>
          )}
        </div>
      </form>

      {error && (
        <div className="mt-6">
          <ErrorAlert error={error} title="The scan could not be completed." />
        </div>
      )}

      <p className="mt-8 text-sm text-slate-600 dark:text-slate-300">
        Not sure where to start?{" "}
        <Link to="/scan/demo" className="font-medium text-accent-500 hover:underline">
          Try a demo page
        </Link>{" "}
        to see each injection technique in action.
      </p>
    </section>
  );
}
