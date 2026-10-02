/**
 * Popup: capture the active tab's page and scan it with ShadowScan.
 *
 * SECURITY: findings contain text from a possibly hostile page. They are only
 * ever placed with textContent, never innerHTML, so nothing in them can run.
 * The page is read only when the user clicks Scan (activeTab), and is sent
 * only to the ShadowPrompt server the user configured.
 */

import {
  errorMessage,
  isScannablePage,
  originPattern,
  resultsPageUrl,
  scanHtml,
  summarise,
  uploadFilename,
} from "./lib.js";

const $ = (id) => document.getElementById(id);

function show(id, visible = true) {
  $(id).hidden = !visible;
}

function setStatus(text) {
  $("status").textContent = text ?? "";
  show("status", Boolean(text));
}

function setError(text) {
  $("error").textContent = text ?? "";
  show("error", Boolean(text));
}

function openOptions(event) {
  event?.preventDefault();
  chrome.runtime.openOptionsPage();
}

/** Read the page as the user sees it, after its scripts ran. */
async function capturePage(tabId) {
  const [injection] = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => ({
      html: `<!doctype html>\n${document.documentElement.outerHTML}`,
      url: location.href,
    }),
  });
  return injection.result;
}

function renderResult(serverUrl, result) {
  const view = summarise(result);
  const score = $("score-value");
  score.textContent = String(view.score);
  score.dataset.severity = view.severity;
  $("severity-label").textContent = view.label;
  $("severity-action").textContent = view.action;

  const list = $("findings");
  list.replaceChildren();
  for (const finding of view.findings) {
    const item = document.createElement("li");
    const title = document.createElement("strong");
    title.textContent = finding.title;
    const where = document.createElement("span");
    where.className = "where";
    where.textContent = ` in ${finding.where}`;
    item.append(title, where);
    if (finding.note) {
      const note = document.createElement("div");
      note.className = "note";
      note.textContent = finding.note;
      item.append(note);
    }
    const evidence = document.createElement("pre");
    evidence.className = "evidence";
    evidence.textContent = finding.evidence;
    item.append(evidence);
    list.append(item);
  }
  if (view.findingCount === 0) {
    const item = document.createElement("li");
    item.textContent = "No detection rule matched anything on this page.";
    list.append(item);
  }
  $("more").textContent = view.hiddenCount ? `${view.hiddenCount} more in the full result.` : "";
  show("more", view.hiddenCount > 0);
  $("report-link").href = resultsPageUrl(serverUrl, view.id);
  show("result");
}

async function scan(serverUrl) {
  setError(null);
  show("result", false);
  const button = $("scan");
  button.disabled = true;
  try {
    // Ask for access to the server's origin only, at the moment it is needed.
    const origins = [originPattern(serverUrl)];
    const granted =
      (await chrome.permissions.contains({ origins })) || (await chrome.permissions.request({ origins }));
    if (!granted) {
      setError("ShadowScan needs permission to contact your ShadowPrompt server.");
      return;
    }

    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id || !isScannablePage(tab.url ?? "")) {
      setError("This page cannot be scanned. Open a web page and try again.");
      return;
    }

    setStatus("Reading the page…");
    let page;
    try {
      page = await capturePage(tab.id);
    } catch {
      setError("The browser does not allow extensions to read this page.");
      return;
    }

    setStatus("Scanning…");
    const result = await scanHtml(fetch, serverUrl, page.html, uploadFilename(page.url));
    setStatus(null);
    renderResult(serverUrl, result);
  } catch (error) {
    setStatus(null);
    setError(errorMessage(error));
  } finally {
    button.disabled = false;
  }
}

async function init() {
  $("options-link").addEventListener("click", openOptions);
  $("open-options").addEventListener("click", openOptions);
  const { serverUrl } = await chrome.storage.sync.get("serverUrl");
  if (!serverUrl) {
    show("setup");
    return;
  }
  $("server-name").textContent = new URL(serverUrl).host;
  show("ready");
  $("scan").addEventListener("click", () => scan(serverUrl));
}

init();
