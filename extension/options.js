/**
 * Settings: the ShadowPrompt address, checked and granted before it is saved.
 */

import { apiBase, normaliseServerUrl, originPattern } from "./lib.js";

const $ = (id) => document.getElementById(id);

function message(id, text) {
  for (const other of ["status", "error"]) {
    $(other).hidden = true;
  }
  $(id).textContent = text;
  $(id).hidden = false;
}

async function load() {
  const { serverUrl } = await chrome.storage.sync.get("serverUrl");
  $("server-url").value = serverUrl ?? "";
}

async function save(event) {
  event.preventDefault();
  const { url, error } = normaliseServerUrl($("server-url").value);
  if (error) {
    message("error", error);
    return;
  }
  const origins = [originPattern(url)];
  const granted = await chrome.permissions.request({ origins });
  if (!granted) {
    message("error", "Permission to contact that address was not granted.");
    return;
  }
  try {
    const response = await fetch(`${apiBase(url)}/scan/capabilities`, { credentials: "omit" });
    if (!response.ok) throw new Error(String(response.status));
  } catch {
    message("error", "Saved, but the server did not answer. Check that ShadowPrompt is running.");
    await chrome.storage.sync.set({ serverUrl: url });
    return;
  }
  await chrome.storage.sync.set({ serverUrl: url });
  message("status", "Saved. ShadowPrompt answered at this address.");
}

$("settings").addEventListener("submit", save);
load();
