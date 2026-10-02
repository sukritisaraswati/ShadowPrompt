/**
 * Campaign results: Security Score, per-level breakdown, and every verdict
 * with its evidence.
 *
 * SECURITY: attack text and model replies are untrusted. They are rendered
 * only as React text nodes, never as markup.
 */

import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { toApiError } from "@/api/client";
import { PROVIDER_LABELS, downloadCampaignReport, getCampaign } from "@/api/lab";
import { ACTIVE_STATUSES, type ApiError, type Campaign, type TestResult, type Verdict } from "@/api/types";
import ErrorAlert from "@/components/ErrorAlert";
import ReportButtons from "@/components/ReportButtons";
import { ScoreDial, SeverityBadge } from "@/components/Severity";
import { RATING_COLOUR, VerdictBadge } from "@/components/Verdict";

type Filter = "all" | "failures" | "unclear";

const FILTERS: Record<Filter, (r: TestResult) => boolean> = {
  all: () => true,
  failures: (r) => r.verdict === "FAIL" || r.verdict === "PARTIAL",
  unclear: (r) => r.verdict === "UNCLEAR",
};

function reasons(result: TestResult): string[] {
  const detail = result.evaluation_detail;
  if (!detail) return [];
  if (detail.error) return [detail.error.message];
  return [...(detail.layer1?.reasons ?? []), ...(detail.layer2?.reasons ?? [])];
}

function Notes({ result }: { result: TestResult }) {
  const detail = result.evaluation_detail;
  if (!detail) return null;
  const notes: string[] = [];
  if (detail.page_scan) {
    const scan = detail.page_scan;
    notes.push(
      scan.score > 0
        ? `ShadowScan rated this attack page ${scan.severity} (${scan.score}/100), finding it in: ${scan.sources.join(", ").replaceAll("_", " ")}${scan.decoded?.length ? ` after decoding ${scan.decoded.join(", ").replaceAll(">", " then ")}` : ""}.`
        : "ShadowScan found nothing on this attack page.",
    );
  }
  if (detail.layer3) {
    notes.push(
      detail.layer3.verdict
        ? `Decided by the Layer 3 judge (${detail.layer3.model ?? "Claude"}${detail.layer3.cached ? ", cached" : ""}): ${detail.layer3.reason}`
        : `Layer 3: ${detail.layer3.reason}`,
    );
  }
  if (notes.length === 0) return null;
  return (
    <ul className="mt-2 space-y-1 text-xs text-slate-600 dark:text-slate-400" data-testid="notes">
      {notes.map((n) => (
        <li key={n}>{n}</li>
      ))}
    </ul>
  );
}

function ResultCard({ result }: { result: TestResult }) {
  return (
    <article className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <VerdictBadge verdict={result.verdict} />
        <h3 className="font-semibold">{result.name}</h3>
        {result.custom_pack && (
          <span className="rounded bg-violet-100 px-1.5 py-0.5 text-xs text-violet-800 dark:bg-violet-900/40 dark:text-violet-200" title={`From the custom pack ${result.custom_pack}`}>
            custom
          </span>
        )}
        {result.language && result.language !== "en" && (
          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs uppercase text-slate-600 dark:bg-slate-800 dark:text-slate-300" title={result.language_name}>
            {result.language}
          </span>
        )}
        <span className="text-sm text-slate-500">
          {result.code} &middot; {result.technique}
        </span>
        {result.latency_ms !== null && <span className="ml-auto text-xs text-slate-500">{result.latency_ms} ms</span>}
      </header>
      <h4 className="mt-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Attack</h4>
      <pre className="evidence mt-1" data-testid="attack">{result.attack_text}</pre>
      <h4 className="mt-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Model response</h4>
      <pre className="evidence mt-1" data-testid="response">{result.response_summary || "(no response)"}</pre>
      <Notes result={result} />
      {reasons(result).length > 0 && (
        <p className="mt-2 text-xs text-slate-600 dark:text-slate-400">
          <span className="font-semibold">Why: </span>
          {reasons(result).join("; ")}
        </p>
      )}
    </article>
  );
}

export default function Results() {
  const { id = "" } = useParams();
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [filter, setFilter] = useState<Filter>("failures");

  useEffect(() => {
    const controller = new AbortController();
    getCampaign(id, controller.signal)
      .then((c) => {
        setCampaign(c);
        if (!c.results.some(FILTERS.failures)) setFilter("all");
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setError(toApiError(cause));
      });
    return () => controller.abort();
  }, [id]);

  if (error) {
    return (
      <section className="max-w-2xl space-y-4">
        <h1 className="text-2xl font-bold tracking-tight">Campaign Results</h1>
        <ErrorAlert error={error} title="This campaign could not be loaded." />
      </section>
    );
  }
  if (!campaign) return <p role="status" className="text-slate-500">Loading campaign&hellip;</p>;

  const running = ACTIVE_STATUSES.has(campaign.status);
  const shown = campaign.results.filter(FILTERS[filter]);
  const count = (v: Verdict) => campaign.results.filter((r) => r.verdict === v).length;

  return (
    <div className="space-y-8">
      <section className="flex flex-col gap-6 sm:flex-row sm:items-center">
        {campaign.rating && campaign.overall_score !== null ? (
          <ScoreDial score={Math.round(campaign.overall_score)} level={RATING_COLOUR[campaign.rating.level]} />
        ) : (
          <div className="flex h-32 w-32 shrink-0 items-center justify-center rounded-full border-8 border-slate-200 text-sm text-slate-500 dark:border-slate-700">No score</div>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight">Campaign Results</h1>
            {campaign.rating && <SeverityBadge level={RATING_COLOUR[campaign.rating.level]} label={campaign.rating.label} />}
          </div>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
            {campaign.session.model_name} via{" "}
            {PROVIDER_LABELS[campaign.session.provider as keyof typeof PROVIDER_LABELS] ?? campaign.session.provider}
            {campaign.session.endpoint_host ? ` (${campaign.session.endpoint_host})` : ""} &middot; levels {campaign.levels_run.join(", ")}
          </p>
          {campaign.rating && (
            <p className="mt-2 text-sm">
              <span className="font-medium">{campaign.rating.interpretation}</span> {campaign.rating.recommendation}
            </p>
          )}
          <p className="mt-1 text-xs text-slate-500">
            {campaign.completed_tests} of {campaign.total_tests} tests run &middot; {count("FAIL")} fail, {count("PARTIAL")} partial,{" "}
            {count("PASS")} pass, {count("UNCLEAR")} unclear &middot; {new Date(campaign.started_at).toLocaleString()}
          </p>
        </div>
        <ReportButtons download={(format) => downloadCampaignReport(id, format)} disabled={running} />
      </section>

      {(campaign.error_message || campaign.status !== "completed") && (
        <p className="rounded-md border border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
          {running ? (
            <>
              This campaign is still running.{" "}
              <Link to={`/lab/running?campaign=${campaign.id}`} className="font-medium underline">
                Watch it live
              </Link>
            </>
          ) : (
            <>Status: {campaign.status}. {campaign.error_message}</>
          )}
        </p>
      )}

      {campaign.config?.target?.kind === "chatbot" && (
        <section role="note" className="rounded-md border border-sky-300 bg-sky-50 px-4 py-3 text-sm text-sky-900 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-100">
          <p>
            Tested as a chatbot ({campaign.config.target.mode === "server" ? "server keeps the conversation" : campaign.config.target.mode === "message" ? "single messages" : "history sent with each request"},{" "}
            {campaign.config.target.canary_planted ? "canary planted" : "no canary"}).
          </p>
          {Object.entries(campaign.config.target.skipped).length > 0 && (
            <ul className="mt-1 list-disc pl-5">
              {Object.entries(campaign.config.target.skipped).map(([why, n]) => (
                <li key={why}>
                  {n} {n === 1 ? "test was" : "tests were"} skipped: {why}.
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {(campaign.track_scores ?? []).length > 0 && (
        <section className="grid gap-3 sm:grid-cols-2">
          {(campaign.track_scores ?? []).map((t) => (
            <div key={t.track} className="rounded-lg border border-slate-200 p-4 dark:border-slate-800" data-testid={`track-${t.track}`}>
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t.name}</div>
              <div className="mt-1 flex items-baseline gap-3">
                <span className="text-3xl font-bold">{t.score === null ? "–" : t.score}</span>
                {t.rating && <SeverityBadge level={RATING_COLOUR[t.rating.level]} label={t.rating.label} />}
              </div>
            </div>
          ))}
        </section>
      )}

      <section>
        <h2 className="text-xl font-semibold">Score by level</h2>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[560px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-800">
                <th className="py-2 pr-3">Level</th>
                <th className="py-2 pr-3">Name</th>
                <th className="py-2 pr-3">Pass</th>
                <th className="py-2 pr-3">Partial</th>
                <th className="py-2 pr-3">Fail</th>
                <th className="py-2 pr-3">Unclear</th>
                <th className="py-2">Score</th>
              </tr>
            </thead>
            <tbody>
              {campaign.level_scores.map((ls) => (
                <tr key={ls.code} className="border-b border-slate-100 dark:border-slate-900">
                  <td className="py-2 pr-3 font-bold text-accent-500">{ls.code}</td>
                  <td className="py-2 pr-3">{ls.name}</td>
                  <td className="py-2 pr-3">{ls.passed}</td>
                  <td className="py-2 pr-3">{ls.partial}</td>
                  <td className="py-2 pr-3">{ls.failed}</td>
                  <td className="py-2 pr-3">{ls.unclear}</td>
                  <td className="py-2 font-semibold">{ls.score === null ? "–" : ls.score}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="mr-auto text-xl font-semibold">Test results</h2>
          {(["failures", "unclear", "all"] as Filter[]).map((f) => (
            <button
              key={f}
              type="button"
              aria-pressed={filter === f}
              onClick={() => setFilter(f)}
              className={`rounded-md px-3 py-1 text-sm ${filter === f ? "bg-accent-500 text-white" : "border border-slate-300 dark:border-slate-700"}`}
            >
              {f === "failures" ? "Failures" : f === "unclear" ? "Needs review" : "All"} ({campaign.results.filter(FILTERS[f]).length})
            </button>
          ))}
        </div>
        <div className="mt-3 space-y-3">
          {shown.length === 0 ? (
            <p className="text-sm text-slate-600 dark:text-slate-300">No tests match this filter.</p>
          ) : (
            shown.map((r) => <ResultCard key={r.id} result={r} />)
          )}
        </div>
      </section>

      <Link to="/lab/configure" className="inline-block text-sm font-medium text-accent-500 hover:underline">
        Run another campaign
      </Link>
    </div>
  );
}
