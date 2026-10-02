/**
 * Past campaigns, with filters, pagination, deletion, and selection for
 * side-by-side comparison.
 */

import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { toApiError } from "@/api/client";
import { PROVIDER_LABELS, deleteCampaign, listCampaigns, type CampaignListParams } from "@/api/lab";
import { ACTIVE_STATUSES, type ApiError, type CampaignStatus, type CampaignSummary, type Page } from "@/api/types";
import ErrorAlert from "@/components/ErrorAlert";
import { SeverityBadge } from "@/components/Severity";
import { RATING_COLOUR } from "@/components/Verdict";

const PAGE_SIZE = 20;
const STATUSES: CampaignStatus[] = ["completed", "stopped", "failed", "running", "paused"];
const FIELD =
  "rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm dark:border-slate-700 dark:bg-shadow-900";

export default function History() {
  const navigate = useNavigate();
  const [page, setPage] = useState<Page<CampaignSummary> | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [offset, setOffset] = useState(0);
  const [model, setModel] = useState("");
  const [status, setStatus] = useState<CampaignStatus | "">("");
  const [minScore, setMinScore] = useState("");
  const [selected, setSelected] = useState<string[]>([]);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      const params: CampaignListParams = { limit: PAGE_SIZE, offset };
      if (model.trim()) params.model_name = model.trim();
      if (status) params.status = status;
      if (minScore !== "") params.min_score = Number(minScore);
      try {
        setPage(await listCampaigns(params, signal));
        setError(null);
      } catch (cause) {
        if (!signal?.aborted) setError(toApiError(cause));
      }
    },
    [offset, model, status, minScore],
  );

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  function toggle(id: string) {
    setSelected((current) =>
      current.includes(id) ? current.filter((x) => x !== id) : current.length < 4 ? [...current, id] : current,
    );
  }

  async function remove(campaign: CampaignSummary) {
    if (!window.confirm(`Delete the campaign for ${campaign.session.model_name}? This cannot be undone.`)) return;
    try {
      await deleteCampaign(campaign.id);
      setSelected((current) => current.filter((x) => x !== campaign.id));
      await load();
    } catch (cause) {
      setError(toApiError(cause));
    }
  }

  const total = page?.pagination.total ?? 0;

  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="mr-auto text-2xl font-bold tracking-tight">Past Campaigns</h1>
        <button
          type="button"
          disabled={selected.length < 2}
          onClick={() => navigate(`/lab/compare?ids=${selected.join(",")}`)}
          className="rounded-md bg-accent-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-600 disabled:opacity-50"
        >
          Compare selected ({selected.length})
        </button>
      </div>

      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          setOffset(0);
        }}
        aria-label="Filter campaigns"
      >
        <label className="text-xs text-slate-500">
          Model
          <input value={model} onChange={(e) => { setModel(e.target.value); setOffset(0); }} placeholder="Any model" className={`${FIELD} block`} />
        </label>
        <label className="text-xs text-slate-500">
          Status
          <select value={status} onChange={(e) => { setStatus(e.target.value as CampaignStatus | ""); setOffset(0); }} className={`${FIELD} block`}>
            <option value="">Any status</option>
            {STATUSES.map((s) => (
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
      </form>

      {error && <ErrorAlert error={error} />}
      {!page && !error && <p role="status" className="text-slate-500">Loading campaigns&hellip;</p>}

      {page && page.items.length === 0 && (
        <p className="text-slate-600 dark:text-slate-300">
          No campaigns match.{" "}
          <Link to="/lab/connect" className="font-medium text-accent-500 hover:underline">
            Run one
          </Link>
          .
        </p>
      )}

      {page && page.items.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-800">
                <th className="py-2 pr-2"><span className="sr-only">Select</span></th>
                <th className="py-2 pr-3">Started</th>
                <th className="py-2 pr-3">Model</th>
                <th className="py-2 pr-3">Levels</th>
                <th className="py-2 pr-3">Tests</th>
                <th className="py-2 pr-3">Score</th>
                <th className="py-2 pr-3">Status</th>
                <th className="py-2"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {page.items.map((c) => {
                const active = ACTIVE_STATUSES.has(c.status);
                return (
                  <tr key={c.id} className="border-b border-slate-100 dark:border-slate-900">
                    <td className="py-2 pr-2">
                      <input
                        type="checkbox"
                        aria-label={`Select ${c.session.model_name} campaign for comparison`}
                        checked={selected.includes(c.id)}
                        disabled={c.overall_score === null || (!selected.includes(c.id) && selected.length >= 4)}
                        onChange={() => toggle(c.id)}
                      />
                    </td>
                    <td className="py-2 pr-3 whitespace-nowrap">{new Date(c.started_at).toLocaleString()}</td>
                    <td className="py-2 pr-3">
                      <div className="font-medium">{c.session.model_name}</div>
                      <div className="text-xs text-slate-500">
                        {PROVIDER_LABELS[c.session.provider as keyof typeof PROVIDER_LABELS] ?? c.session.provider}
                      </div>
                    </td>
                    <td className="py-2 pr-3">{c.levels_run.join(", ")}</td>
                    <td className="py-2 pr-3">
                      {c.completed_tests}/{c.total_tests}
                    </td>
                    <td className="py-2 pr-3">
                      {c.overall_score === null || !c.rating ? (
                        "–"
                      ) : (
                        <span className="flex items-center gap-2">
                          <span className="font-semibold">{c.overall_score}</span>
                          <SeverityBadge level={RATING_COLOUR[c.rating.level]} label={c.rating.label} />
                        </span>
                      )}
                    </td>
                    <td className="py-2 pr-3">{c.status}</td>
                    <td className="py-2 whitespace-nowrap text-right">
                      <Link
                        to={active ? `/lab/running?campaign=${c.id}` : `/lab/results/${c.id}`}
                        className="font-medium text-accent-500 hover:underline"
                      >
                        {active ? "Watch" : "View"}
                      </Link>
                      {!active && (
                        <button type="button" onClick={() => remove(c)} className="ml-3 text-rose-600 hover:underline dark:text-rose-400">
                          Delete
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
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
