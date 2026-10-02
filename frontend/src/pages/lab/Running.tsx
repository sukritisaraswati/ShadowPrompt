/**
 * Live campaign progress.
 *
 * Verdicts arrive over Server-Sent Events: a snapshot first, then one event
 * per result and status change. If the browser has no EventSource, or the
 * stream fails, the page falls back to polling, so progress is never lost.
 */

import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { toApiError } from "@/api/client";
import { campaignStreamUrl, getCampaign, pauseCampaign, resumeCampaign, stopCampaign } from "@/api/lab";
import { ACTIVE_STATUSES, type ApiError, type Campaign, type CampaignEvent, type Verdict } from "@/api/types";
import ErrorAlert from "@/components/ErrorAlert";
import { VerdictBadge } from "@/components/Verdict";

export const POLL_MS = 1500;

type Transport = "connecting" | "live" | "polling";

function applyEvent(current: Campaign | null, event: CampaignEvent): Campaign | null {
  if (event.type === "snapshot") return event.campaign;
  if (!current) return current;
  if (event.type === "result") {
    if (current.results.some((r) => r.id === event.result.id)) return current;
    return {
      ...current,
      results: [...current.results, event.result],
      completed_tests: current.completed_tests + 1,
      current_level: event.result.code,
    };
  }
  if (event.type === "status") return { ...current, status: event.status };
  return current;
}

export default function Running() {
  const [params] = useSearchParams();
  const campaignId = params.get("campaign") ?? "";
  const navigate = useNavigate();
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [transport, setTransport] = useState<Transport>("connecting");
  const [pending, setPending] = useState<"stop" | "pause" | "resume" | null>(null);
  const finished = useRef(false);

  useEffect(() => {
    if (!campaignId) return;
    finished.current = false;
    const controller = new AbortController();
    let source: EventSource | null = null;
    let timer: number | undefined;

    async function finish() {
      if (finished.current) return;
      finished.current = true;
      source?.close();
      try {
        const final = await getCampaign(campaignId, controller.signal);
        setCampaign(final);
        if (final.status === "completed") navigate(`/lab/results/${final.id}`, { replace: true });
      } catch (cause) {
        if (!controller.signal.aborted) setError(toApiError(cause));
      }
    }

    async function poll() {
      setTransport("polling");
      try {
        const latest = await getCampaign(campaignId, controller.signal);
        setCampaign(latest);
        if (ACTIVE_STATUSES.has(latest.status)) {
          timer = window.setTimeout(poll, POLL_MS);
        } else {
          await finish();
        }
      } catch (cause) {
        if (!controller.signal.aborted) setError(toApiError(cause));
      }
    }

    function stream() {
      if (typeof window.EventSource === "undefined") {
        poll();
        return;
      }
      source = new window.EventSource(campaignStreamUrl(campaignId));
      const handle = (message: MessageEvent<string>) => {
        const event = JSON.parse(message.data) as CampaignEvent;
        if (event.type === "done") {
          finish();
        } else if (event.type === "resync") {
          source?.close();
          stream();
        } else {
          setTransport("live");
          setCampaign((current) => applyEvent(current, event));
        }
      };
      for (const type of ["snapshot", "result", "status", "done", "resync"]) {
        source.addEventListener(type, handle as EventListener);
      }
      source.onerror = () => {
        if (finished.current) return;
        source?.close();
        poll();
      };
    }

    stream();
    return () => {
      controller.abort();
      source?.close();
      window.clearTimeout(timer);
    };
  }, [campaignId, navigate]);

  // Clear a pending control once the status it asked for arrives.
  useEffect(() => {
    if (pending === "pause" && campaign?.status === "paused") setPending(null);
    if (pending === "resume" && campaign?.status === "running") setPending(null);
  }, [campaign?.status, pending]);

  async function control(action: "stop" | "pause" | "resume") {
    setPending(action);
    try {
      const call = { stop: stopCampaign, pause: pauseCampaign, resume: resumeCampaign }[action];
      await call(campaignId);
    } catch (cause) {
      setError(toApiError(cause));
      setPending(null);
    }
  }

  if (!campaignId) {
    return (
      <section className="max-w-2xl">
        <h1 className="text-2xl font-bold tracking-tight">Live Test Run</h1>
        <p className="mt-2 text-slate-600 dark:text-slate-300">No campaign is selected.</p>
        <Link to="/lab/configure" className="mt-3 inline-block text-sm font-medium text-accent-500 hover:underline">
          Set up a campaign
        </Link>
      </section>
    );
  }

  const done = campaign?.completed_tests ?? 0;
  const total = campaign?.total_tests ?? 0;
  const percent = total ? Math.round((done / total) * 100) : 0;
  const counts = (campaign?.results ?? []).reduce(
    (acc, r) => ({ ...acc, [r.verdict]: (acc[r.verdict] ?? 0) + 1 }),
    {} as Partial<Record<Verdict, number>>,
  );
  const active = campaign ? ACTIVE_STATUSES.has(campaign.status) : true;
  const paused = campaign?.status === "paused";
  const button = "rounded-md border px-3 py-1.5 text-sm font-medium disabled:opacity-60";

  return (
    <section className="max-w-4xl space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold tracking-tight">Live Test Run</h1>
        {campaign && (
          <span className="rounded-full border border-slate-300 px-2.5 py-0.5 text-xs font-medium dark:border-slate-700">
            {campaign.status}
          </span>
        )}
        {active && (
          <span className="text-xs text-slate-500" data-testid="transport">
            {transport === "live" ? "● Live" : transport === "polling" ? "Refreshing every few seconds" : "Connecting…"}
          </span>
        )}
        {active && campaign && (
          <div className="ml-auto flex gap-2">
            {paused ? (
              <button type="button" onClick={() => control("resume")} disabled={pending !== null} className={`${button} border-accent-500 text-accent-600 dark:text-accent-400`}>
                {pending === "resume" ? "Resuming…" : "Resume"}
              </button>
            ) : (
              <button type="button" onClick={() => control("pause")} disabled={pending !== null} className={`${button} border-slate-400`}>
                {pending === "pause" ? "Pausing after this test…" : "Pause"}
              </button>
            )}
            <button type="button" onClick={() => control("stop")} disabled={pending === "stop"} className={`${button} border-rose-400 text-rose-700 dark:text-rose-300`}>
              {pending === "stop" ? "Stopping…" : "Stop campaign"}
            </button>
          </div>
        )}
      </div>

      {error && <ErrorAlert error={error} />}

      {!campaign && !error && <p role="status" className="text-slate-500">Starting&hellip;</p>}

      {campaign && (
        <>
          <p className="text-sm text-slate-600 dark:text-slate-300">
            {campaign.session.model_name} &middot; levels {campaign.levels_run.join(", ")}
            {campaign.current_level ? ` · now on ${campaign.current_level}` : ""}
            {paused ? " · paused" : ""}
          </p>

          <div>
            <div className="flex justify-between text-sm">
              <span>
                {done} of {total} tests
              </span>
              <span>{percent}%</span>
            </div>
            <div className="mt-1 h-2.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100} aria-label="Campaign progress">
              <div className={`h-full transition-all ${paused ? "bg-slate-400" : "bg-accent-500"}`} style={{ width: `${percent}%` }} />
            </div>
          </div>

          <div className="flex flex-wrap gap-3 text-sm">
            {(["PASS", "PARTIAL", "FAIL", "UNCLEAR"] as Verdict[]).map((v) => (
              <span key={v} className="flex items-center gap-1.5">
                <VerdictBadge verdict={v} /> {counts[v] ?? 0}
              </span>
            ))}
          </div>

          {!active && (
            <div className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100">
              <p className="font-semibold">The campaign {campaign.status === "stopped" ? "was stopped" : "ended early"}.</p>
              {campaign.error_message && <p className="mt-1">{campaign.error_message}</p>}
              <p className="mt-1">Results for the {done} completed tests have been saved.</p>
              <Link to={`/lab/results/${campaign.id}`} className="mt-2 inline-block font-medium underline">
                View results
              </Link>
            </div>
          )}

          <ol className="divide-y divide-slate-200 rounded-md border border-slate-200 dark:divide-slate-800 dark:border-slate-800" aria-label="Verdicts so far">
            {[...campaign.results].reverse().map((r) => (
              <li key={r.id} className="flex items-center gap-3 px-3 py-2 text-sm">
                <VerdictBadge verdict={r.verdict} />
                <span className="w-10 shrink-0 text-xs text-slate-500">{r.code}</span>
                <span className="flex-1">{r.name}</span>
                <span className="text-xs text-slate-500">{r.technique}</span>
              </li>
            ))}
          </ol>
        </>
      )}
    </section>
  );
}
