/** Save a report returned by the API as a file in the browser. */

import { http } from "./client";
import type { ReportFormat } from "./types";

export async function downloadReport(
  url: string,
  body: Record<string, unknown>,
  format: ReportFormat,
  filename: string,
): Promise<void> {
  const response = await http.post<Blob>(url, { ...body, format }, { responseType: "blob", timeout: 120_000 });
  const href = URL.createObjectURL(response.data);
  try {
    const link = document.createElement("a");
    link.href = href;
    link.download = `${filename}.${format}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    URL.revokeObjectURL(href);
  }
}
