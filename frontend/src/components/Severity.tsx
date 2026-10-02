import type { Severity } from "@/api/types";

export const SEVERITY_STYLES: Record<Severity, { badge: string; text: string; stroke: string }> = {
  clean: { badge: "bg-sev-clean", text: "text-sev-clean", stroke: "stroke-sev-clean" },
  low: { badge: "bg-sev-low", text: "text-sev-low", stroke: "stroke-sev-low" },
  medium: { badge: "bg-sev-medium", text: "text-sev-medium", stroke: "stroke-sev-medium" },
  high: { badge: "bg-sev-high", text: "text-sev-high", stroke: "stroke-sev-high" },
  critical: { badge: "bg-sev-critical", text: "text-sev-critical", stroke: "stroke-sev-critical" },
};

export function SeverityBadge({ level, label }: { level: Severity; label: string }) {
  return (
    <span
      data-severity={level}
      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold text-white ${SEVERITY_STYLES[level].badge}`}
    >
      {label}
    </span>
  );
}

/** A 0-100 score drawn as a ring, coloured by severity band. */
export function ScoreDial({ score, level }: { score: number; level: Severity }) {
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(100, score));
  return (
    <figure className="relative h-32 w-32 shrink-0" aria-label={`Risk score ${clamped} out of 100`}>
      <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90" aria-hidden="true">
        <circle cx="50" cy="50" r={radius} strokeWidth="9" fill="none" className="stroke-slate-200 dark:stroke-slate-700" />
        <circle
          cx="50"
          cy="50"
          r={radius}
          strokeWidth="9"
          fill="none"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - clamped / 100)}
          className={SEVERITY_STYLES[level].stroke}
        />
      </svg>
      <figcaption className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={`text-3xl font-bold ${SEVERITY_STYLES[level].text}`}>{clamped}</span>
        <span className="text-xs text-slate-500">/ 100</span>
      </figcaption>
    </figure>
  );
}
