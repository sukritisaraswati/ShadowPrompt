/**
 * Scaffold page used throughout Phase 0.
 *
 * Each route in the blueprint exists and is reachable from day one, and says
 * which release fills it in. Pages are replaced one at a time as the releases
 * land; nothing here ships to end users as-is.
 */

interface PlaceholderPageProps {
  title: string;
  release: string;
  summary: string;
  /** What this page will let the user do once implemented. */
  willDo?: string[];
}

export default function PlaceholderPage({
  title,
  release,
  summary,
  willDo = [],
}: PlaceholderPageProps) {
  return (
    <section className="max-w-3xl">
      <div className="mb-3 flex items-center gap-3">
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        <span className="rounded-full border border-amber-400 px-2.5 py-0.5 text-xs font-medium text-amber-700 dark:text-amber-400">
          {release}
        </span>
      </div>

      <p className="text-slate-600 dark:text-slate-300">{summary}</p>

      {willDo.length > 0 && (
        <>
          <h2 className="mt-6 mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Planned behaviour
          </h2>
          <ul className="list-inside list-disc space-y-1 text-sm text-slate-600 dark:text-slate-300">
            {willDo.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
