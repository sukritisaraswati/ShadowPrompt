/**
 * Custom test packs: upload a team's own tests, review them, delete them.
 *
 * SECURITY: pack names and test names are user content. They are rendered
 * only as React text, never as markup.
 */

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { toApiError } from "@/api/client";
import {
  deletePack,
  getPack,
  listPacks,
  PACK_EXAMPLE_URL,
  PACK_SCHEMA_URL,
  uploadPack,
  validatePackFile,
} from "@/api/lab";
import type { ApiError, PayloadPack, PayloadPackSummary } from "@/api/types";
import ErrorAlert from "@/components/ErrorAlert";

function levelsLabel(counts: Record<string, number>): string {
  return Object.entries(counts)
    .map(([code, n]) => `${code}×${n}`)
    .join(" · ");
}

function PackRow({ pack, onDeleted }: { pack: PayloadPackSummary; onDeleted: () => void }) {
  const [detail, setDetail] = useState<PayloadPack | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  async function toggle() {
    if (detail) {
      setDetail(null);
      return;
    }
    try {
      setDetail(await getPack(pack.id));
    } catch (cause) {
      setError(toApiError(cause));
    }
  }

  async function remove() {
    if (!window.confirm(`Delete the pack "${pack.name}"? Campaigns that ran it keep their results.`)) return;
    setBusy(true);
    try {
      await deletePack(pack.id);
      onDeleted();
    } catch (cause) {
      setError(toApiError(cause));
      setBusy(false);
    }
  }

  return (
    <li className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="font-semibold">{pack.name}</h3>
        <span className="text-sm text-slate-500">
          {pack.test_count} {pack.test_count === 1 ? "test" : "tests"} · {levelsLabel(pack.level_counts)}
        </span>
        <span className="ml-auto flex gap-3 text-sm">
          <button type="button" onClick={toggle} className="text-accent-500 hover:underline" aria-expanded={detail !== null}>
            {detail ? "Hide tests" : "Show tests"}
          </button>
          <button type="button" onClick={remove} disabled={busy} className="text-rose-600 hover:underline disabled:opacity-60 dark:text-rose-400">
            Delete
          </button>
        </span>
      </div>
      {pack.description && <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{pack.description}</p>}
      {error && (
        <div className="mt-2">
          <ErrorAlert error={error} />
        </div>
      )}
      {detail && (
        <table className="mt-3 w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="py-1 pr-3">Test</th>
              <th className="py-1 pr-3">Level</th>
              <th className="py-1 pr-3">Objective</th>
              <th className="py-1">Language</th>
            </tr>
          </thead>
          <tbody>
            {detail.tests.map((t) => (
              <tr key={t.id} className="border-t border-slate-100 dark:border-slate-800">
                <td className="py-1 pr-3">{t.name}</td>
                <td className="py-1 pr-3">{t.code}</td>
                <td className="py-1 pr-3">{t.objective}</td>
                <td className="py-1 uppercase">{t.language}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </li>
  );
}

export default function Packs() {
  const [packs, setPacks] = useState<PayloadPackSummary[] | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [validation, setValidation] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [uploaded, setUploaded] = useState<PayloadPack | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback((signal?: AbortSignal) => {
    listPacks(signal)
      .then(setPacks)
      .catch((cause: unknown) => {
        if (!signal?.aborted) setError(toApiError(cause));
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setUploaded(null);
    const problem = validatePackFile(file);
    setValidation(problem);
    if (problem || !file) return;
    setBusy(true);
    try {
      setUploaded(await uploadPack(file));
      refresh();
    } catch (cause) {
      setError(toApiError(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="max-w-3xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Custom tests</h1>
        <p className="mt-2 text-slate-600 dark:text-slate-300">
          Add your own tests to the Lab, written for your deployment. A pack is a JSON file of up to 50 tests at
          Levels 1 to 4. Each test gives the model something to protect and names the evidence of failure, just
          like the built-in tests, so verdicts stay unambiguous. Choose packs when you{" "}
          <Link to="/lab/configure" className="text-accent-500 hover:underline">
            set up a campaign
          </Link>
          .
        </p>
        <p className="mt-2 text-sm">
          <a href={PACK_EXAMPLE_URL} download="shadowprompt-pack-example.json" className="text-accent-500 hover:underline">
            Download an example pack
          </a>{" "}
          ·{" "}
          <a href={PACK_SCHEMA_URL} target="_blank" rel="noreferrer" className="text-accent-500 hover:underline">
            JSON Schema
          </a>
        </p>
      </div>

      <form onSubmit={onSubmit} noValidate className="space-y-3 rounded-lg border border-slate-200 p-4 dark:border-slate-800">
        <label htmlFor="pack-file" className="block text-sm font-semibold">
          Pack file (.json, up to 256 KB)
        </label>
        <input
          id="pack-file"
          type="file"
          accept=".json,application/json"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          disabled={busy}
          className="block text-sm"
        />
        {validation && (
          <p role="alert" className="text-sm text-rose-700 dark:text-rose-400">
            {validation}
          </p>
        )}
        <button type="submit" disabled={busy} className="rounded-md bg-accent-500 px-4 py-2 text-sm font-medium text-white hover:bg-accent-600 disabled:opacity-60">
          {busy ? "Checking…" : "Upload pack"}
        </button>
      </form>

      {error && <ErrorAlert error={error} title="The pack was not accepted." />}
      {uploaded && (
        <p role="status" className="rounded-md border border-emerald-300 bg-emerald-50 px-4 py-3 text-sm text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-100">
          {uploaded.name}: {uploaded.test_count} {uploaded.test_count === 1 ? "test" : "tests"} checked and ready.
        </p>
      )}

      <div>
        <h2 className="text-lg font-semibold">Your packs</h2>
        {packs === null && !error && <p role="status" className="mt-2 text-sm text-slate-500">Loading&hellip;</p>}
        {packs?.length === 0 && <p className="mt-2 text-sm text-slate-500">No packs yet.</p>}
        <ul className="mt-3 space-y-3">
          {packs?.map((pack) => <PackRow key={pack.id} pack={pack} onDeleted={() => refresh()} />)}
        </ul>
      </div>
    </section>
  );
}
