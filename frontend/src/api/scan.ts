/** ShadowScan API calls. */

import { get, post } from "./client";
import { downloadReport } from "./download";
import type { DemoPage, Page, ReportFormat, ScanResult, ScanSummary, Severity } from "./types";

/** Mirrors the backend upload ceiling so users get instant feedback. */
export const MAX_UPLOAD_BYTES = 2 * 1024 * 1024;
export const ALLOWED_EXTENSIONS = [".html", ".htm"];

/** Scans fetch pages and parse documents, so allow longer than the default. */
const SCAN_TIMEOUT_MS = 60_000;

export function scanUrl(url: string, signal?: AbortSignal): Promise<ScanResult> {
  return post<ScanResult>("/scan/url", { url }, { signal, timeout: SCAN_TIMEOUT_MS });
}

export function scanFile(file: File, signal?: AbortSignal): Promise<ScanResult> {
  const form = new FormData();
  form.append("file", file);
  return post<ScanResult>("/scan/html", form, { signal, timeout: SCAN_TIMEOUT_MS });
}

export function scanDemo(demoId: string, signal?: AbortSignal): Promise<ScanResult> {
  return post<ScanResult>(`/scan/demo-pages/${encodeURIComponent(demoId)}/scan`, undefined, {
    signal,
  });
}

export function getScan(id: string, signal?: AbortSignal): Promise<ScanResult> {
  return get<ScanResult>(`/scan/results/${encodeURIComponent(id)}`, { signal });
}

export interface ScanListParams {
  limit?: number;
  offset?: number;
  severity?: Severity;
  min_score?: number;
  max_score?: number;
}

export function listScans(params: ScanListParams = {}, signal?: AbortSignal) {
  return get<Page<ScanSummary>>("/scan/results", { params, signal });
}

export function listDemoPages(signal?: AbortSignal): Promise<DemoPage[]> {
  return get<DemoPage[]>("/scan/demo-pages", { signal });
}

/** Download the scan report as HTML or PDF. */
export function downloadScanReport(scanId: string, format: ReportFormat = "html"): Promise<void> {
  return downloadReport("/scan/reports", { scan_id: scanId }, format, `shadowscan-${scanId.slice(0, 8)}`);
}

/** Client-side checks that mirror the server's, for immediate feedback. */
export function validateScanFile(file: File): string | null {
  const name = file.name.toLowerCase();
  if (!ALLOWED_EXTENSIONS.some((ext) => name.endsWith(ext))) {
    return "Only .html and .htm files can be scanned.";
  }
  if (file.size === 0) return "The file is empty.";
  if (file.size > MAX_UPLOAD_BYTES) return "Files larger than 2 MB cannot be scanned.";
  return null;
}

export function validateScanUrl(value: string): string | null {
  const url = value.trim();
  if (!url) return "Enter a URL to scan.";
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return "Enter a full URL, starting with http:// or https://.";
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return "Only http and https URLs can be scanned.";
  }
  return null;
}
