/**
 * One ShadowScan result: score, severity, findings, and the report download.
 *
 * SECURITY: evidence is text taken from a hostile page. It is rendered only
 * through React text nodes, which escape it. Nothing on this page may use
 * dangerouslySetInnerHTML, and a test enforces that a script tag in evidence
 * stays inert.
 */

import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { toApiError } from "@/api/client";
import { downloadScanReport, getScan } from "@/api/scan";
import type { ApiError, Finding, ScanResult } from "@/api/types";
import ErrorAlert from "@/components/ErrorAlert";
import ReportButtons from "@/components/ReportButtons";
import { ScoreDial, SeverityBadge } from "@/components/Severity";

function targetLabel(result: ScanResult): string {
  if (result.source_kind === "url") return result.target_url ?? "Unknown URL";
  if (result.source_kind === "demo") return `Demo page: ${result.target_filename ?? ""}`;
  return result.target_filename ?? "Uploaded file";
}

function FindingCard({ finding, index }: { finding: Finding; index: number }) {
  return (
    <article className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-sm font-semibold text-slate-400">#{index}</span>
        <h3 className="font-semibold">{finding.category_label}</h3>
        <span className="text-sm text-slate-500">
          in {finding.source_label}
          {finding.locator ? ` · ${finding.locator}` : ""}
        </span>
        <span className="ml-auto text-xs text-slate-500">risk weight {finding.risk_weight}</span>
      </header>

      <p className="mt-1 text-xs text-slate-500">{finding.rule_description}</p>

      <h4 className="mt-3 flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
        Evidence
        {finding.obfuscation_label && (
          <span className="rounded bg-amber-100 px-1.5 py-0.5 normal-case tracking-normal text-amber-900 dark:bg-amber-900/40 dark:text-amber-200">
            {finding.obfuscation_note ?? `Decoded from ${finding.obfuscation_label}`}
          </span>
        )}
      </h4>
      <pre className="evidence mt-1" data-testid="evidence">
        {finding.evidence_text}
      </pre>

      <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">Impact</dt>
          <dd className="mt-0.5 text-slate-700 dark:text-slate-300">{finding.impact}</dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">How to fix</dt>
          <dd className="mt-0.5 text-slate-700 dark:text-slate-300">{finding.remediation}</dd>
        </div>
      </dl>
    </article>
  );
}

export default function ScanResults() {
  const { id = "" } = useParams();
  const [result, setResult] = useState<ScanResult | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setResult(null);
    setError(null);
    getScan(id, controller.signal)
      .then(setResult)
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setError(toApiError(cause));
      });
    return () => controller.abort();
  }, [id]);

  if (error) {
    return (
      <section className="max-w-2xl space-y-4">
        <h1 className="text-2xl font-bold tracking-tight">Scan results</h1>
        <ErrorAlert error={error} title="This scan could not be loaded." />
        <Link to="/scan" className="text-sm font-medium text-accent-500 hover:underline">
          Start a new scan
        </Link>
      </section>
    );
  }

  if (!result) {
    return (
      <p role="status" className="text-slate-500">
        Loading scan&hellip;
      </p>
    );
  }

  const sourcesWithFindings = new Set(result.findings.map((f) => f.source_location)).size;
  const checklist = Array.from(
    new Map(result.findings.map((f) => [f.category, `${f.category_label}: ${f.remediation}`])).values(),
  );

  return (
    <div className="space-y-8">
      <section className="flex flex-col gap-6 sm:flex-row sm:items-center">
        <ScoreDial score={result.score} level={result.severity.level} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight">Scan results</h1>
            <SeverityBadge level={result.severity.level} label={result.severity.label} />
          </div>
          <p className="mt-1 break-all font-mono text-sm text-slate-600 dark:text-slate-300">
            {targetLabel(result)}
          </p>
          <p className="mt-2 text-sm">
            <span className="font-medium">{result.severity.meaning}</span>{" "}
            {result.severity.recommended_action}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            {result.finding_count} {result.finding_count === 1 ? "finding" : "findings"} across{" "}
            {sourcesWithFindings} source {sourcesWithFindings === 1 ? "location" : "locations"}
            {result.extraction_summary ? ` · ${result.extraction_summary.segments} text segments analysed` : ""}
            {" · "}
            {new Date(result.created_at).toLocaleString()}
          </p>
        </div>
        <ReportButtons download={(format) => downloadScanReport(id, format)} />
      </section>

      {result.extraction_summary?.rendered && (
        <p
          className={`rounded-md border px-4 py-2 text-sm ${
            result.extraction_summary.rendered.error
              ? "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200"
              : "border-slate-200 text-slate-600 dark:border-slate-800 dark:text-slate-300"
          }`}
        >
          {result.extraction_summary.rendered.error
            ? `The page's JavaScript could not be run: ${result.extraction_summary.rendered.error} Only the static HTML was scanned.`
            : `The page's JavaScript was run in a sandboxed browser: ${result.extraction_summary.rendered.requests} scripts and files loaded, ${result.extraction_summary.rendered.blocked} requests refused. ${result.extraction_summary.rendered.added_findings ?? 0} of the findings were added by scripts.`}
        </p>
      )}

      {result.extraction_summary?.truncated && (
        <p className="rounded-md border border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
          This page was very large, so scan limits were reached and part of it was not analysed.
        </p>
      )}

      <section>
        <h2 className="text-xl font-semibold">Findings</h2>
        {result.findings.length === 0 ? (
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
            No detection rule matched any content on this page.
          </p>
        ) : (
          <div className="mt-3 space-y-3">
            {result.findings.map((finding, i) => (
              <FindingCard key={finding.id} finding={finding} index={i + 1} />
            ))}
          </div>
        )}
      </section>

      {checklist.length > 0 && (
        <section>
          <h2 className="text-xl font-semibold">Remediation checklist</h2>
          <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-slate-700 dark:text-slate-300">
            {checklist.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="rounded-md border border-slate-200 p-4 text-sm dark:border-slate-800">
        <h2 className="font-semibold">Limitations</h2>
        <ul className="mt-2 list-inside list-disc space-y-1 text-slate-600 dark:text-slate-300">
          {result.limitations.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>

      <Link to="/scan" className="inline-block text-sm font-medium text-accent-500 hover:underline">
        Scan another page
      </Link>
    </div>
  );
}
