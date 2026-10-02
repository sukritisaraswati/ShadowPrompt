/**
 * Lab Home -- platform overview and entry points to both services.
 *
 * The backend status strip doubles as the Phase 0 proof that the frontend,
 * the Vite proxy and the API are wired together.
 */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { fetchHealth, toApiError } from "@/api/client";
import { ATTACK_LEVELS, type ApiError, type HealthResponse } from "@/api/types";

function BackendStatus() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then(setHealth)
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        setError(toApiError(cause));
      });
    return () => controller.abort();
  }, []);

  if (error) {
    return (
      <p
        role="status"
        className="rounded-md border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-200"
      >
        Backend unreachable: {error.message}
      </p>
    );
  }

  if (!health) {
    return (
      <p role="status" className="text-sm text-slate-500">
        Checking backend&hellip;
      </p>
    );
  }

  return (
    <p
      role="status"
      className="rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200"
    >
      Backend {health.status} &middot; v{health.version} &middot; database {health.database}
    </p>
  );
}

function ServiceCard({
  title,
  description,
  to,
  cta,
}: {
  title: string;
  description: string;
  to: string;
  cta: string;
}) {
  return (
    <article className="flex flex-col rounded-lg border border-slate-200 p-5 dark:border-slate-800">
      <h3 className="text-lg font-semibold">{title}</h3>
      <p className="mt-2 flex-1 text-sm text-slate-600 dark:text-slate-300">{description}</p>
      <Link
        to={to}
        className="mt-4 self-start rounded-md bg-accent-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-600"
      >
        {cta}
      </Link>
    </article>
  );
}

export default function Home() {
  return (
    <div className="space-y-10">
      <section>
        <h1 className="text-3xl font-bold tracking-tight">ShadowPrompt</h1>
        <p className="mt-2 max-w-3xl text-slate-600 dark:text-slate-300">
          A defensive LLM security testing lab. Connect a model and run a structured
          battery of attacks, or scan a webpage for content designed to manipulate any
          model that reads it.
        </p>
        <div className="mt-4 max-w-md">
          <BackendStatus />
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2">
        <ServiceCard
          title="ShadowPrompt Lab"
          description="Connect your LLM via API and run level 1 through 5 attack campaigns, from basic jailbreaks to chained multi-vector attacks. Produces a scored security report."
          to="/lab/connect"
          cta="Connect a model"
        />
        <ServiceCard
          title="ShadowScan"
          description="Paste a URL or upload an HTML file and get an analysis of how dangerous that page is for any LLM that might read it. Connects to no model at all."
          to="/scan"
          cta="Scan a page"
        />
      </section>

      <section>
        <h2 className="text-xl font-semibold">The five attack levels</h2>
        <ul className="mt-3 space-y-2">
          {ATTACK_LEVELS.map(({ level, name, danger }) => (
            <li
              key={level}
              className="flex items-center gap-3 rounded-md border border-slate-200 px-3 py-2 text-sm dark:border-slate-800"
            >
              <span className="w-6 shrink-0 text-center font-bold text-accent-500">{level}</span>
              <span className="flex-1 font-medium">{name}</span>
              <span className="text-slate-500">{danger}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
