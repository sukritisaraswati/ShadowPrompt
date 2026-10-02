/**
 * Demo Lab: crafted pages that show each injection technique safely.
 */

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { toApiError } from "@/api/client";
import { listDemoPages, scanDemo } from "@/api/scan";
import type { ApiError, DemoPage } from "@/api/types";
import ErrorAlert from "@/components/ErrorAlert";
import { SeverityBadge } from "@/components/Severity";

const SEVERITY_LABEL = {
  clean: "Clean",
  low: "Low",
  medium: "Medium",
  high: "High",
  critical: "Critical",
} as const;

export default function DemoLab() {
  const navigate = useNavigate();
  const [pages, setPages] = useState<DemoPage[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [running, setRunning] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    listDemoPages(controller.signal)
      .then(setPages)
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setError(toApiError(cause));
      });
    return () => controller.abort();
  }, []);

  async function run(page: DemoPage) {
    setRunning(page.id);
    setError(null);
    try {
      const result = await scanDemo(page.id);
      navigate(`/scan/results/${result.id}`);
    } catch (cause) {
      setError(toApiError(cause));
      setRunning(null);
    }
  }

  return (
    <section>
      <h1 className="text-2xl font-bold tracking-tight">Demo Lab</h1>
      <p className="mt-2 max-w-3xl text-slate-600 dark:text-slate-300">
        Each page below hides an injection in a different place. Scanning one shows what
        ShadowScan finds and why it matters. The pages are fixed content on the server, so no
        external site is fetched.
      </p>

      {error && (
        <div className="mt-4">
          <ErrorAlert error={error} />
        </div>
      )}

      {!pages && !error && (
        <p role="status" className="mt-6 text-slate-500">
          Loading demo pages&hellip;
        </p>
      )}

      {pages && (
        <ul className="mt-6 grid gap-4 sm:grid-cols-2">
          {pages.map((page) => (
            <li
              key={page.id}
              className="flex flex-col rounded-lg border border-slate-200 p-4 dark:border-slate-800"
            >
              <div className="flex items-start justify-between gap-3">
                <h2 className="font-semibold">{page.title}</h2>
                <SeverityBadge
                  level={page.expected_severity}
                  label={SEVERITY_LABEL[page.expected_severity]}
                />
              </div>
              <p className="mt-1 text-xs text-slate-500">
                Technique: {page.technique} &middot; expected findings: {page.expected_findings}
              </p>
              <p className="mt-2 flex-1 text-sm text-slate-600 dark:text-slate-300">
                {page.description}
              </p>
              <button
                type="button"
                onClick={() => run(page)}
                disabled={running !== null}
                className="mt-4 self-start rounded-md bg-accent-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-600 disabled:opacity-60"
              >
                {running === page.id ? "Scanning…" : `Scan ${page.title}`}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
