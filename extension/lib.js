/**
 * Pure helpers for the ShadowScan browser extension.
 *
 * Kept free of browser-extension APIs so they run under Node's test runner.
 * Nothing here builds HTML from strings: findings are page content from a
 * possibly hostile site and are only ever set as text by the popup.
 */

/** The server's upload limit for one page. */
export const MAX_PAGE_BYTES = 2 * 1024 * 1024;

export const SEVERITIES = ["clean", "low", "medium", "high", "critical"];

/**
 * Validate and tidy the ShadowPrompt URL a user typed.
 * Returns { url } or { error }.
 */
export function normaliseServerUrl(input) {
  const text = String(input ?? "").trim();
  if (!text) return { error: "Enter the address of your ShadowPrompt server." };
  let parsed;
  try {
    parsed = new URL(text);
  } catch {
    return { error: "Enter a full address, for example http://localhost:8080." };
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return { error: "The address must start with http:// or https://." };
  }
  if (parsed.username || parsed.password) {
    return { error: "Do not put credentials in the address." };
  }
  const path = parsed.pathname.replace(/\/+$/, "");
  return { url: `${parsed.origin}${path}` };
}

/** The origin pattern the extension needs permission for. */
export function originPattern(serverUrl) {
  return `${new URL(serverUrl).origin}/*`;
}

export function apiBase(serverUrl) {
  return `${serverUrl}/api/v1`;
}

export function resultsPageUrl(serverUrl, scanId) {
  return `${serverUrl}/scan/results/${encodeURIComponent(scanId)}`;
}

/** Pages the extension cannot or should not read. */
export function isScannablePage(url) {
  try {
    const { protocol } = new URL(url);
    return protocol === "http:" || protocol === "https:" || protocol === "file:";
  } catch {
    return false;
  }
}

/** A safe upload filename from the page address, ending in .html. */
export function uploadFilename(pageUrl) {
  let base = "page";
  try {
    const url = new URL(pageUrl);
    base = `${url.hostname}${url.pathname}`.replace(/\/+$/, "") || "page";
  } catch {
    // keep the default
  }
  const safe = base.replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^[._]+/, "").slice(0, 120) || "page";
  return safe.toLowerCase().endsWith(".html") ? safe : `${safe}.html`;
}

export function byteLength(text) {
  return new TextEncoder().encode(text).length;
}

/** A readable message for an API error envelope or a network failure. */
export function errorMessage(error) {
  if (error && typeof error === "object" && "code" in error) {
    const hints = {
      UPLOAD_TOO_LARGE: "This page is larger than the 2 MB scan limit.",
      RATE_LIMITED: "Too many scans in a short time. Wait a minute and try again.",
      UNSUPPORTED_FILE_TYPE: "The server could not read this page as HTML.",
    };
    return hints[error.code] ?? error.message ?? "The scan failed.";
  }
  return "Could not reach your ShadowPrompt server. Check the address in the extension options.";
}

/**
 * Upload a page's HTML to ShadowScan.
 * `fetchImpl` is injected so tests and the popup share one code path.
 */
export async function scanHtml(fetchImpl, serverUrl, html, filename) {
  if (byteLength(html) > MAX_PAGE_BYTES) {
    throw { code: "UPLOAD_TOO_LARGE", message: "This page is larger than the 2 MB scan limit." };
  }
  const form = new FormData();
  form.append("file", new Blob([html], { type: "text/html" }), filename);
  let response;
  try {
    response = await fetchImpl(`${apiBase(serverUrl)}/scan/html`, {
      method: "POST",
      body: form,
      credentials: "omit",
    });
  } catch {
    throw { code: "SERVER_UNREACHABLE", message: errorMessage(null) };
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw {
      code: body.code ?? `HTTP_${response.status}`,
      message: body.message ?? `The server answered ${response.status}.`,
    };
  }
  return body;
}

/** What the popup shows for a scan result: plain values, no markup. */
export function summarise(result, limit = 5) {
  const findings = (result.findings ?? []).slice(0, limit).map((f) => ({
    title: f.category_label,
    where: f.source_label,
    note: f.obfuscation_note ?? null,
    evidence: String(f.evidence_text ?? "").slice(0, 300),
  }));
  return {
    id: result.id,
    score: result.score,
    severity: SEVERITIES.includes(result.severity?.level) ? result.severity.level : "clean",
    label: result.severity?.label ?? "",
    action: result.severity?.recommended_action ?? "",
    findingCount: result.finding_count ?? findings.length,
    hiddenCount: Math.max(0, (result.finding_count ?? 0) - findings.length),
    findings,
  };
}
