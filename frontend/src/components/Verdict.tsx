import type { Rating, Severity, Verdict } from "@/api/types";

const VERDICT_STYLES: Record<Verdict, string> = {
  PASS: "bg-sev-clean",
  PARTIAL: "bg-sev-medium",
  FAIL: "bg-sev-critical",
  UNCLEAR: "bg-slate-500",
};

const VERDICT_LABELS: Record<Verdict, string> = {
  PASS: "Pass",
  PARTIAL: "Partial",
  FAIL: "Fail",
  UNCLEAR: "Unclear",
};

export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  return (
    <span
      data-verdict={verdict}
      className={`inline-block min-w-14 rounded-full px-2 py-0.5 text-center text-xs font-semibold text-white ${VERDICT_STYLES[verdict]}`}
    >
      {VERDICT_LABELS[verdict]}
    </span>
  );
}

/** Lab ratings reuse the ShadowScan colour scale so both services read alike. */
export const RATING_COLOUR: Record<Rating, Severity> = {
  secure: "clean",
  moderate: "medium",
  vulnerable: "high",
  critical: "critical",
};
