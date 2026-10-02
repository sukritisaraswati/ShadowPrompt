/** ShadowPrompt Lab API calls. */

import type { LlmConnection } from "@/context/SessionContext";

import { API_BASE, del, get, post } from "./client";
import { downloadReport } from "./download";
import type {
  Campaign,
  CampaignStarted,
  CampaignStatus,
  CampaignSummary,
  ConnectionTestResult,
  Page,
  PayloadLibrarySummary,
  ReportFormat,
} from "./types";

/**
 * The connection as the backend expects it. The key goes in the request body
 * to our own backend only; the browser never contacts the model directly.
 */
function connectionBody(connection: LlmConnection) {
  return {
    provider: connection.provider,
    base_url: connection.baseUrl,
    model: connection.modelName,
    api_key: connection.apiKey || null,
  };
}

export function testConnection(
  connection: LlmConnection,
  signal?: AbortSignal,
): Promise<ConnectionTestResult> {
  return post<ConnectionTestResult>("/lab/connect/test", connectionBody(connection), {
    signal,
    timeout: 45_000,
  });
}

export interface CampaignOptions {
  levels: number[];
  sampleSize: number | null;
  timeoutSeconds: number;
  maxRetries: number;
}

export function startCampaign(
  sessionId: string,
  connection: LlmConnection,
  options: CampaignOptions,
): Promise<CampaignStarted> {
  return post<CampaignStarted>("/lab/campaigns", {
    session_id: sessionId,
    connection: connectionBody(connection),
    levels: options.levels,
    sample_size: options.sampleSize,
    timeout_seconds: options.timeoutSeconds,
    max_retries: options.maxRetries,
  });
}

export function getCampaign(id: string, signal?: AbortSignal): Promise<Campaign> {
  return get<Campaign>(`/lab/campaigns/${encodeURIComponent(id)}`, { signal });
}

export interface CampaignListParams {
  limit?: number;
  offset?: number;
  model_name?: string;
  status?: CampaignStatus;
  min_score?: number;
  max_score?: number;
}

export function listCampaigns(params: CampaignListParams = {}, signal?: AbortSignal) {
  return get<Page<CampaignSummary>>("/lab/campaigns", { params, signal });
}

export function stopCampaign(id: string): Promise<unknown> {
  return post(`/lab/campaigns/${encodeURIComponent(id)}/stop`);
}

export function pauseCampaign(id: string): Promise<unknown> {
  return post(`/lab/campaigns/${encodeURIComponent(id)}/pause`);
}

export function resumeCampaign(id: string): Promise<unknown> {
  return post(`/lab/campaigns/${encodeURIComponent(id)}/resume`);
}

export function deleteCampaign(id: string): Promise<unknown> {
  return del(`/lab/campaigns/${encodeURIComponent(id)}`);
}

/** URL of the Server-Sent Events stream for a campaign. */
export function campaignStreamUrl(id: string): string {
  return `${API_BASE}/lab/campaigns/${encodeURIComponent(id)}/stream`;
}

export function getPayloadSummary(signal?: AbortSignal): Promise<PayloadLibrarySummary> {
  return get<PayloadLibrarySummary>("/lab/payload-library/summary", { signal });
}

/** Download the campaign report as HTML or PDF. */
export function downloadCampaignReport(campaignId: string, format: ReportFormat = "html"): Promise<void> {
  return downloadReport("/lab/reports", { campaign_id: campaignId }, format, `shadowprompt-campaign-${campaignId.slice(0, 8)}`);
}

export interface ProviderPreset {
  id: string;
  label: string;
  provider: LlmConnection["provider"];
  baseUrl: string;
  model: string;
  needsKey: boolean;
}

export const PROVIDER_PRESETS: ProviderPreset[] = [
  { id: "openai", label: "OpenAI", provider: "openai_compatible", baseUrl: "https://api.openai.com/v1", model: "gpt-4o-mini", needsKey: true },
  { id: "groq", label: "Groq", provider: "openai_compatible", baseUrl: "https://api.groq.com/openai/v1", model: "llama-3.1-8b-instant", needsKey: true },
  { id: "together", label: "Together AI", provider: "openai_compatible", baseUrl: "https://api.together.xyz/v1", model: "meta-llama/Llama-3.3-70B-Instruct-Turbo", needsKey: true },
  { id: "openrouter", label: "OpenRouter", provider: "openai_compatible", baseUrl: "https://openrouter.ai/api/v1", model: "openai/gpt-4o-mini", needsKey: true },
  { id: "anthropic", label: "Anthropic Claude", provider: "anthropic", baseUrl: "https://api.anthropic.com", model: "claude-haiku-4-5-20251001", needsKey: true },
  { id: "gemini", label: "Google Gemini", provider: "gemini", baseUrl: "https://generativelanguage.googleapis.com", model: "gemini-2.5-flash", needsKey: true },
  { id: "azure", label: "Azure OpenAI", provider: "azure_openai", baseUrl: "https://YOUR-RESOURCE.openai.azure.com/openai/deployments/YOUR-DEPLOYMENT", model: "deployment", needsKey: true },
  { id: "custom", label: "Custom OpenAI-compatible endpoint", provider: "openai_compatible", baseUrl: "", model: "", needsKey: false },
];

export const PROVIDER_LABELS: Record<LlmConnection["provider"], string> = {
  openai_compatible: "OpenAI-compatible",
  anthropic: "Anthropic",
  gemini: "Google Gemini",
  azure_openai: "Azure OpenAI",
};
