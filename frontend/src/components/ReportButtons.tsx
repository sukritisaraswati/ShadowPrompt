import { useState } from "react";

import { toApiError } from "@/api/client";
import type { ApiError, ReportFormat } from "@/api/types";
import ErrorAlert from "@/components/ErrorAlert";

/** HTML and PDF report downloads with their own busy and error states. */
export default function ReportButtons({
  download,
  disabled = false,
}: {
  download: (format: ReportFormat) => Promise<void>;
  disabled?: boolean;
}) {
  const [busy, setBusy] = useState<ReportFormat | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  async function run(format: ReportFormat) {
    setBusy(format);
    setError(null);
    try {
      await download(format);
    } catch (cause) {
      setError(toApiError(cause));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-2 sm:items-end">
      <div className="flex gap-2">
        {(["html", "pdf"] as ReportFormat[]).map((format) => (
          <button
            key={format}
            type="button"
            onClick={() => run(format)}
            disabled={disabled || busy !== null}
            className={
              format === "html"
                ? "rounded-md bg-accent-500 px-4 py-2 text-sm font-medium text-white hover:bg-accent-600 disabled:opacity-60"
                : "rounded-md border border-accent-500 px-4 py-2 text-sm font-medium text-accent-600 hover:bg-accent-500/10 disabled:opacity-60 dark:text-accent-400"
            }
          >
            {busy === format ? "Preparing\u2026" : `Download ${format.toUpperCase()} report`}
          </button>
        ))}
      </div>
      {error && <ErrorAlert error={error} title="The report could not be generated." />}
    </div>
  );
}
