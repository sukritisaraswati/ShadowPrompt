/**
 * Campaign setup: choose levels, optional language packs and custom test
 * packs, full suite or sample, timeouts and retries.
 */

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { toApiError } from "@/api/client";
import { getPayloadSummary, listPacks, startCampaign } from "@/api/lab";
import type { ApiError, PayloadLibrarySummary, PayloadPackSummary } from "@/api/types";
import ErrorAlert from "@/components/ErrorAlert";
import { describeConnection, useSession } from "@/context/SessionContext";

const NUMBER =
  "mt-1 w-28 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-shadow-900";

export default function Configure() {
  const navigate = useNavigate();
  const { connection, isVerified, sessionId } = useSession();
  const [library, setLibrary] = useState<PayloadLibrarySummary | null>(null);
  const [levels, setLevels] = useState<number[]>([1]);
  const [languages, setLanguages] = useState<string[]>([]);
  const [packs, setPacks] = useState<PayloadPackSummary[]>([]);
  const [packIds, setPackIds] = useState<string[]>([]);
  const [mode, setMode] = useState<"full" | "sample">("full");
  const [sampleSize, setSampleSize] = useState(5);
  const [timeoutSeconds, setTimeoutSeconds] = useState(30);
  const [maxRetries, setMaxRetries] = useState(1);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  const connected = Boolean(isVerified && connection && sessionId);

  useEffect(() => {
    // Nothing to set up until a model is connected.
    if (!connected) return;
    const controller = new AbortController();
    getPayloadSummary(controller.signal)
      .then(setLibrary)
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setError(toApiError(cause));
      });
    // Custom packs are optional: if they cannot be listed, the section stays hidden.
    listPacks(controller.signal)
      .then(setPacks)
      .catch(() => undefined);
    return () => controller.abort();
  }, [connected]);

  const testCount = useMemo(() => {
    if (!library) return 0;
    const added = [
      ...(library.languages ?? []).filter((p) => languages.includes(p.code)),
      ...packs.filter((p) => packIds.includes(p.id)),
    ];
    return library.levels
      .filter((l) => levels.includes(l.level))
      .reduce((sum, l) => {
        const pool = l.test_count + added.reduce((n, p) => n + (p.level_counts[String(l.level)] ?? 0), 0);
        return sum + (mode === "sample" ? Math.min(sampleSize, pool) : pool);
      }, 0);
  }, [library, levels, languages, packs, packIds, mode, sampleSize]);

  if (!isVerified || !connection || !sessionId) {
    return (
      <section className="max-w-2xl">
        <h1 className="text-2xl font-bold tracking-tight">Campaign Setup</h1>
        <p className="mt-3 text-slate-600 dark:text-slate-300">
          Connect a model first. The connection is held in this tab only, so it is needed
          again after a reload.
        </p>
        <Link to="/lab/connect" className="mt-4 inline-block rounded-md bg-accent-500 px-4 py-2 text-sm font-medium text-white hover:bg-accent-600">
          Connect a model
        </Link>
      </section>
    );
  }

  function toggle(level: number) {
    setLevels((current) =>
      current.includes(level) ? current.filter((l) => l !== level) : [...current, level].sort(),
    );
  }

  function toggleLanguage(code: string) {
    setLanguages((current) =>
      current.includes(code) ? current.filter((c) => c !== code) : [...current, code],
    );
  }

  function togglePack(id: string) {
    setPackIds((current) => (current.includes(id) ? current.filter((p) => p !== id) : [...current, id]));
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!connection || !sessionId || levels.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const started = await startCampaign(sessionId, connection, {
        levels,
        sampleSize: mode === "sample" ? sampleSize : null,
        timeoutSeconds,
        maxRetries,
        languages,
        customPackIds: packIds,
      });
      navigate(`/lab/running?campaign=${started.campaign_id}`);
    } catch (cause) {
      setError(toApiError(cause));
      setBusy(false);
    }
  }

  return (
    <section className="max-w-3xl">
      <h1 className="text-2xl font-bold tracking-tight">Campaign Setup</h1>
      <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
        Testing <span className="font-medium">{describeConnection(connection)}</span>.{" "}
        <Link to="/lab/connect" className="text-accent-500 hover:underline">
          Change
        </Link>
      </p>

      <form onSubmit={onSubmit} className="mt-6 space-y-6">
        <fieldset>
          <legend className="text-sm font-semibold">Attack levels</legend>
          {!library && !error && <p role="status" className="mt-2 text-sm text-slate-500">Loading the test library&hellip;</p>}
          <ul className="mt-2 space-y-2">
            {library?.levels.map((l) => (
              <li key={l.level}>
                <label
                  className={`flex items-center gap-3 rounded-md border px-3 py-2 text-sm ${
                    l.available ? "border-slate-200 dark:border-slate-800" : "border-dashed border-slate-300 opacity-60 dark:border-slate-700"
                  }`}
                >
                  <input type="checkbox" checked={levels.includes(l.level)} disabled={!l.available || busy} onChange={() => toggle(l.level)} />
                  <span className="w-5 font-bold text-accent-500">{l.level}</span>
                  <span className="flex-1 font-medium">{l.name}</span>
                  <span className="text-xs text-slate-500">
                    {l.available ? `${l.test_count} tests · ${l.danger} danger` : "Arrives in Release 3"}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </fieldset>

        {library?.languages && library.languages.length > 0 && (
          <fieldset>
            <legend className="text-sm font-semibold">Languages</legend>
            <p className="mt-1 text-xs text-slate-500">
              English tests always run. Add tests written in other languages: a model that refuses an attack in
              English can still fall for the same attack in a language it was less carefully aligned in. Each pack
              adds one test to each of Levels 1 to 4.
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              {library.languages.map((pack) => (
                <label
                  key={pack.code}
                  className={`flex cursor-pointer items-center gap-2 rounded-full border px-3 py-1 text-sm ${
                    languages.includes(pack.code)
                      ? "border-accent-500 bg-accent-500/10"
                      : "border-slate-200 dark:border-slate-800"
                  }`}
                >
                  <input
                    type="checkbox"
                    className="sr-only"
                    checked={languages.includes(pack.code)}
                    onChange={() => toggleLanguage(pack.code)}
                    disabled={busy}
                  />
                  {pack.name}
                </label>
              ))}
            </div>
          </fieldset>
        )}

        <fieldset>
          <legend className="text-sm font-semibold">Custom tests</legend>
          {packs.length === 0 ? (
            <p className="mt-1 text-xs text-slate-500">
              No custom packs yet.{" "}
              <Link to="/lab/packs" className="text-accent-500 hover:underline">
                Upload your own tests
              </Link>{" "}
              to run them alongside the library.
            </p>
          ) : (
            <>
              <p className="mt-1 text-xs text-slate-500">
                A pack's tests run at their own levels, so select those levels too.{" "}
                <Link to="/lab/packs" className="text-accent-500 hover:underline">
                  Manage packs
                </Link>
              </p>
              <ul className="mt-2 space-y-2">
                {packs.map((pack) => (
                  <li key={pack.id}>
                    <label className="flex items-center gap-3 rounded-md border border-slate-200 px-3 py-2 text-sm dark:border-slate-800">
                      <input type="checkbox" checked={packIds.includes(pack.id)} onChange={() => togglePack(pack.id)} disabled={busy} />
                      <span className="flex-1 font-medium">{pack.name}</span>
                      <span className="text-xs text-slate-500">
                        {pack.test_count} {pack.test_count === 1 ? "test" : "tests"} at level
                        {Object.keys(pack.level_counts).length === 1 ? " " : "s "}
                        {Object.keys(pack.level_counts).join(", ")}
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            </>
          )}
        </fieldset>

        <fieldset>
          <legend className="text-sm font-semibold">Coverage</legend>
          <div className="mt-2 flex flex-wrap items-end gap-6 text-sm">
            <label className="flex items-center gap-2">
              <input type="radio" name="mode" checked={mode === "full"} onChange={() => setMode("full")} disabled={busy} />
              Every test in each level
            </label>
            <label className="flex items-center gap-2">
              <input type="radio" name="mode" checked={mode === "sample"} onChange={() => setMode("sample")} disabled={busy} />
              A sample of
            </label>
            <label className="text-xs text-slate-500">
              Tests per level
              <input type="number" min={1} max={40} value={sampleSize} onChange={(e) => setSampleSize(Math.max(1, Math.min(40, Number(e.target.value) || 1)))} disabled={busy || mode !== "sample"} className={`${NUMBER} block`} />
            </label>
          </div>
        </fieldset>

        <fieldset className="flex flex-wrap gap-6">
          <legend className="sr-only">Limits</legend>
          <label className="text-sm font-semibold">
            Timeout per test (seconds)
            <input type="number" min={5} max={120} value={timeoutSeconds} onChange={(e) => setTimeoutSeconds(Math.max(5, Math.min(120, Number(e.target.value) || 30)))} disabled={busy} className={`${NUMBER} block font-normal`} />
          </label>
          <label className="text-sm font-semibold">
            Retries on rate limits or errors
            <input type="number" min={0} max={3} value={maxRetries} onChange={(e) => setMaxRetries(Math.max(0, Math.min(3, Number(e.target.value) || 0)))} disabled={busy} className={`${NUMBER} block font-normal`} />
          </label>
        </fieldset>

        <div className="rounded-md border border-slate-200 p-4 text-sm dark:border-slate-800">
          <p>
            This campaign will send <span className="font-semibold">{testCount}</span> requests to your model, one at a time.
            Each test asks it to break a harmless rule, such as revealing a made-up access code, so no harmful content is
            requested. Requests count toward your provider's usage and billing.
          </p>
        </div>

        {error && <ErrorAlert error={error} title="The campaign could not be started." />}

        <button type="submit" disabled={busy || levels.length === 0 || !library} className="rounded-md bg-accent-500 px-4 py-2 text-sm font-medium text-white hover:bg-accent-600 disabled:opacity-60">
          {busy ? "Starting…" : `Start campaign (${testCount} tests)`}
        </button>
      </form>
    </section>
  );
}
