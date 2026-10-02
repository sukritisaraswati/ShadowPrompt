/**
 * Side-by-side comparison of two to four campaigns.
 *
 * The first campaign selected is the baseline. Level scores show the change
 * from it, and the test table lists every test whose verdict differs between
 * campaigns, so it is clear what got better or worse between model versions.
 */

import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { toApiError } from "@/api/client";
import { getCampaign } from "@/api/lab";
import type { ApiError, Campaign, Verdict } from "@/api/types";
import ErrorAlert from "@/components/ErrorAlert";
import { SeverityBadge } from "@/components/Severity";
import { RATING_COLOUR, VerdictBadge } from "@/components/Verdict";

const LEVEL_NAMES: Record<number, string> = {
  1: "Basic Jailbreak",
  2: "Persona & Role",
  3: "Adversarial Design",
  4: "Indirect Injection",
  5: "Chained Attacks",
};
const RANK: Partial<Record<Verdict, number>> = { PASS: 2, PARTIAL: 1, FAIL: 0 };

export interface TestChange {
  payloadId: string;
  name: string;
  level: number;
  verdicts: (Verdict | null)[];
  direction: "improved" | "regressed" | "mixed";
}

/** Tests whose verdict differs across campaigns, relative to the first. */
export function compareTests(campaigns: Campaign[]): TestChange[] {
  const byPayload = new Map<string, { name: string; level: number; verdicts: (Verdict | null)[] }>();
  campaigns.forEach((c, index) => {
    for (const r of c.results) {
      const entry = byPayload.get(r.payload_id) ?? {
        name: r.name,
        level: r.level,
        verdicts: Array<Verdict | null>(campaigns.length).fill(null),
      };
      entry.verdicts[index] = r.verdict;
      byPayload.set(r.payload_id, entry);
    }
  });

  const changes: TestChange[] = [];
  for (const [payloadId, entry] of byPayload) {
    const ranked = entry.verdicts.map((v) => (v ? RANK[v] : undefined));
    const base = ranked[0];
    if (base === undefined) continue;
    const others = ranked.slice(1).filter((r): r is number => r !== undefined);
    if (others.length === 0 || others.every((r) => r === base)) continue;
    const up = others.some((r) => r > base);
    const down = others.some((r) => r < base);
    changes.push({
      payloadId,
      name: entry.name,
      level: entry.level,
      verdicts: entry.verdicts,
      direction: up && down ? "mixed" : up ? "improved" : "regressed",
    });
  }
  return changes.sort((a, b) => a.level - b.level || a.payloadId.localeCompare(b.payloadId));
}

function delta(value: number | null | undefined, base: number | null | undefined) {
  if (value == null || base == null) return null;
  const d = Math.round((value - base) * 10) / 10;
  if (d === 0) return <span className="text-xs text-slate-500">(&plusmn;0)</span>;
  return (
    <span className={`text-xs font-medium ${d > 0 ? "text-sev-clean" : "text-sev-critical"}`}>
      ({d > 0 ? "+" : ""}
      {d})
    </span>
  );
}

export default function Compare() {
  const [params] = useSearchParams();
  const ids = useMemo(
    () => (params.get("ids") ?? "").split(",").map((s) => s.trim()).filter(Boolean).slice(0, 4),
    [params],
  );
  const [campaigns, setCampaigns] = useState<Campaign[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    if (ids.length < 2) return;
    const controller = new AbortController();
    Promise.all(ids.map((id) => getCampaign(id, controller.signal)))
      .then(setCampaigns)
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setError(toApiError(cause));
      });
    return () => controller.abort();
  }, [ids]);

  const changes = useMemo(() => (campaigns ? compareTests(campaigns) : []), [campaigns]);

  if (ids.length < 2) {
    return (
      <section className="max-w-2xl">
        <h1 className="text-2xl font-bold tracking-tight">Model Comparison</h1>
        <p className="mt-2 text-slate-600 dark:text-slate-300">
          Choose two to four scored campaigns in the campaign history, then select{" "}
          <span className="font-medium">Compare selected</span>.
        </p>
        <Link to="/lab/history" className="mt-4 inline-block rounded-md bg-accent-500 px-4 py-2 text-sm font-medium text-white hover:bg-accent-600">
          Open campaign history
        </Link>
      </section>
    );
  }

  if (error) {
    return (
      <section className="max-w-2xl space-y-4">
        <h1 className="text-2xl font-bold tracking-tight">Model Comparison</h1>
        <ErrorAlert error={error} title="One of the campaigns could not be loaded." />
      </section>
    );
  }

  if (!campaigns) return <p role="status" className="text-slate-500">Loading campaigns&hellip;</p>;

  const base = campaigns[0];
  const levels = Array.from(new Set(campaigns.flatMap((c) => c.levels_run))).sort();
  const improved = changes.filter((c) => c.direction === "improved").length;
  const regressed = changes.filter((c) => c.direction === "regressed").length;

  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-2xl font-bold tracking-tight">Model Comparison</h1>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
          Compared with the baseline, {improved} {improved === 1 ? "test" : "tests"} improved and {regressed}{" "}
          {regressed === 1 ? "test" : "tests"} regressed.
        </p>
      </section>

      <section className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left dark:border-slate-800">
              <th className="py-2 pr-3 text-xs uppercase tracking-wide text-slate-500">Measure</th>
              {campaigns.map((c, i) => (
                <th key={c.id} className="py-2 pr-3 align-bottom">
                  <div className="text-xs font-normal text-slate-500">{i === 0 ? "Baseline" : `Campaign ${i + 1}`}</div>
                  <Link to={`/lab/results/${c.id}`} className="font-semibold text-accent-500 hover:underline">
                    {c.session.model_name}
                  </Link>
                  <div className="text-xs font-normal text-slate-500">{new Date(c.started_at).toLocaleDateString()}</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-slate-100 dark:border-slate-900">
              <td className="py-2 pr-3 font-medium">Security Score</td>
              {campaigns.map((c) => (
                <td key={c.id} className="py-2 pr-3">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="text-lg font-bold">{c.overall_score ?? "–"}</span>
                    {c.rating && <SeverityBadge level={RATING_COLOUR[c.rating.level]} label={c.rating.label} />}
                    {c !== base && delta(c.overall_score, base.overall_score)}
                  </span>
                </td>
              ))}
            </tr>
            {levels.map((level) => (
              <tr key={level} className="border-b border-slate-100 dark:border-slate-900">
                <td className="py-2 pr-3">
                  <span className="font-bold text-accent-500">{level}</span> {LEVEL_NAMES[level]}
                </td>
                {campaigns.map((c) => {
                  const score = c.level_scores.find((ls) => ls.level === level)?.score ?? null;
                  const baseScore = base.level_scores.find((ls) => ls.level === level)?.score ?? null;
                  return (
                    <td key={c.id} className="py-2 pr-3">
                      {score === null ? <span className="text-slate-400">not run</span> : score}{" "}
                      {c !== base && delta(score, baseScore)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h2 className="text-xl font-semibold">Tests that changed</h2>
        {changes.length === 0 ? (
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
            Every test the campaigns share had the same verdict.
          </p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-800">
                  <th className="py-2 pr-3">Test</th>
                  <th className="py-2 pr-3">Change</th>
                  {campaigns.map((c, i) => (
                    <th key={c.id} className="py-2 pr-3">
                      {i === 0 ? "Baseline" : `Campaign ${i + 1}`}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {changes.map((change) => (
                  <tr key={change.payloadId} className="border-b border-slate-100 dark:border-slate-900">
                    <td className="py-2 pr-3">
                      <div>{change.name}</div>
                      <div className="text-xs text-slate-500">Level {change.level}</div>
                    </td>
                    <td className="py-2 pr-3">
                      <span
                        className={
                          change.direction === "improved"
                            ? "text-sev-clean"
                            : change.direction === "regressed"
                              ? "text-sev-critical"
                              : "text-sev-medium"
                        }
                      >
                        {change.direction}
                      </span>
                    </td>
                    {change.verdicts.map((v, i) => (
                      <td key={campaigns[i].id} className="py-2 pr-3">
                        {v ? <VerdictBadge verdict={v} /> : <span className="text-xs text-slate-400">not run</span>}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
