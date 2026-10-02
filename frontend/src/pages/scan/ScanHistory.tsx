/**
 * Past ShadowScan results, filterable by severity and score.
 */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { toApiError } from "@/api/client";
import { listScans, type ScanListParams } from "@/api/scan";
import type { ApiError, Page, ScanSummary, Severity } from "@/api/types";
import ErrorAlert from "@/components/ErrorAlert";
import { SeverityBadge } from "@/components/Severity";

const PAGE_SIZE = 20;
const SEVERITIES: Severity[] = ["critical", "high", "medium", "low", "clean"];
const FIELD =
  "rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm dark:border-slate-700 dark:bg-shadow-900";

function target(scan: ScanSummary): string {
  if (scan.source_kind === "url") return scan.target_url ?? "Unknown URL";
  if (scan.source_kind === "demo") return `Demo: ${scan.target_filename ?? ""}`;
  return scan.target_filename ?? "Uploaded file";
}

export default function ScanHistory() {
  const [page, setPage] = useState<Page<ScanSummary> | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [offset, setOffset] = useState(0);
  const [severity, setSeverity] = useState<Severity | "">("");
  const [minScore, setMinScore] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    const params: ScanListParams = { limit: PAGE_SIZE, offset };
    if (severity) params.severity = severity;
    if (minScore !== "") params.min_score = Number(minScore);
    listScans(params, controller.signal)
      .then((p) => {
        setPage(p);
        setError(null);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setError(toApiError(cause));
      });
    return () => controller.abort();
  }, [offset, severity, minScore]);

  const total = page?.pagination.total ?? 0;

  return (
    <section className="space-y-5">
      <h1 className="text-2xl font-bold tracking-tight">Scan History</h1>

      <div className="flex flex-wrap items-end gap-3" role="group" aria-label="Filter scans">
        <label className="text-xs text-slate-500">
          Severity
          <select value={severity} onChange={(e) => { setSeverity(e.target.value as Severity | ""); setOffset(0); }} className={`${FIELD} block`}>
            <option value="">Any severity</option>
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-slate-500">
          Minimum score
          <input type="number" min={0} max={100} value={minScore} onChange={(e) => { setMinScore(e.target.value); setOffset(0); }} className={`${FIELD} block w-28`} />
        </label>
      </div>

      {error && <ErrorAlert error={error} />}
      {!page && !error && <p role="status" className="text-slate-500">Loading scans&hellip;</p>}

      {page && page.items.length === 0 && (
        <p className="text-slate-600 dark:text-slate-300">
          No scans match.{" "}
          <Link to="/scan" className="font-medium text-accent-500 hover:underline">
            Scan a page
          </Link>
          .
        </p>
      )}

      {page && page.items.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-800">
                <th className="py-2 pr-3">Scanned</th>
                <th className="py-2 pr-3">Target</th>
                <th className="py-2 pr-3">Score</th>
                <th className="py-2 pr-3">Findings</th>
                <th className="py-2"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {page.items.map((s) => (
                <tr key={s.id} className="border-b border-slate-100 dark:border-slate-900">
                  <td className="py-2 pr-3 whitespace-nowrap">{new Date(s.created_at).toLocaleString()}</td>
                  <td className="max-w-md truncate py-2 pr-3 font-mono text-xs" title={target(s)}>
                    {target(s)}
                  </td>
                  <td className="py-2 pr-3">
                    <span className="flex items-center gap-2">
                      <span className="font-semibold">{s.score}</span>
                      <SeverityBadge level={s.severity.level} label={s.severity.label} />
                    </span>
                  </td>
                  <td className="py-2 pr-3">{s.finding_count}</td>
                  <td className="py-2 text-right">
                    <Link to={`/scan/results/${s.id}`} className="font-medium text-accent-500 hover:underline">
                      View
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {page && total > PAGE_SIZE && (
        <nav className="flex items-center gap-3 text-sm" aria-label="Pagination">
          <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} className="rounded-md border border-slate-300 px-3 py-1 disabled:opacity-50 dark:border-slate-700">
            Previous
          </button>
          <span>
            {offset + 1}&ndash;{Math.min(offset + PAGE_SIZE, total)} of {total}
          </span>
          <button type="button" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)} className="rounded-md border border-slate-300 px-3 py-1 disabled:opacity-50 dark:border-slate-700">
            Next
          </button>
        </nav>
      )}
    </section>
  );
}
