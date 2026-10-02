/**
 * Types mirroring the backend contract in `app/schemas/common.py`.
 *
 * Kept hand-written rather than generated so the frontend has a single,
 * reviewable definition of what it expects from the API.
 */

export type ErrorCode =
  // Generic
  | "VALIDATION_ERROR"
  | "NOT_FOUND"
  | "INTERNAL_ERROR"
  | "RATE_LIMITED"
  | "NOT_IMPLEMENTED"
  | "CONFLICT"
  // ShadowScan
  | "BLOCKED_TARGET"
  | "FETCH_FAILED"
  | "FETCH_TIMEOUT"
  | "RESPONSE_TOO_LARGE"
  | "UPLOAD_TOO_LARGE"
  | "UNSUPPORTED_FILE_TYPE"
  // Lab
  | "LLM_AUTH_FAILED"
  | "LLM_UNREACHABLE"
  | "LLM_MODEL_NOT_FOUND"
  | "LLM_RATE_LIMITED"
  | "LLM_TIMEOUT"
  // Client-side only: the request never reached the server.
  | "NETWORK_ERROR";

/**
 * Runtime companion to {@link ErrorCode}.
 *
 * Needed because an AxiosError also carries `code` and `message` strings, so
 * shape alone cannot distinguish a backend envelope from a transport error.
 */
export const ERROR_CODES = [
  "VALIDATION_ERROR",
  "NOT_FOUND",
  "INTERNAL_ERROR",
  "RATE_LIMITED",
  "NOT_IMPLEMENTED",
  "CONFLICT",
  "BLOCKED_TARGET",
  "FETCH_FAILED",
  "FETCH_TIMEOUT",
  "RESPONSE_TOO_LARGE",
  "UPLOAD_TOO_LARGE",
  "UNSUPPORTED_FILE_TYPE",
  "LLM_AUTH_FAILED",
  "LLM_UNREACHABLE",
  "LLM_MODEL_NOT_FOUND",
  "LLM_RATE_LIMITED",
  "LLM_TIMEOUT",
  "NETWORK_ERROR",
] as const satisfies readonly ErrorCode[];

export interface ApiError {
  code: ErrorCode;
  message: string;
  detail?: string | null;
}

export type ServiceStatus = "ok" | "degraded" | "down";

export interface HealthResponse {
  status: ServiceStatus;
  version: string;
  environment: string;
  uptime_seconds: number;
  database: ServiceStatus;
  timestamp: string;
}

export interface PaginationMeta {
  total: number;
  limit: number;
  offset: number;
}

export interface Page<T> {
  items: T[];
  pagination: PaginationMeta;
}

/** Verdict for a single Lab test case (blueprint 5.2). */
export type Verdict = "PASS" | "FAIL" | "PARTIAL" | "UNCLEAR";

/** ShadowScan risk bands (blueprint 6.3). */
export type Severity = "clean" | "low" | "medium" | "high" | "critical";

export type CampaignStatus =
  | "pending"
  | "running"
  | "paused"
  | "completed"
  | "stopped"
  | "failed";

export const ACTIVE_STATUSES: ReadonlySet<CampaignStatus> = new Set(["pending", "running", "paused"]);

/** The five attack levels (blueprint section 4). */
export type AttackLevel = 1 | 2 | 3 | 4 | 5;

export const ATTACK_LEVELS: ReadonlyArray<{
  level: AttackLevel;
  name: string;
  danger: string;
}> = [
  { level: 1, name: "Basic Jailbreak", danger: "Low" },
  { level: 2, name: "Persona & Role Manipulation", danger: "Medium" },
  { level: 3, name: "Adversarial Instruction Design", danger: "High" },
  { level: 4, name: "Indirect Injection via Web Content", danger: "Very High" },
  { level: 5, name: "Chained & Multi-Vector Attacks", danger: "Critical" },
];

// --------------------------------------------------------------------------
// ShadowScan (mirrors app/schemas/scan.py)
// --------------------------------------------------------------------------

export type ScanSourceKind = "url" | "upload" | "demo";

export interface SeverityInfo {
  level: Severity;
  label: string;
  meaning: string;
  recommended_action: string;
}

export interface Finding {
  id: string;
  source_location: string;
  source_label: string;
  category: string;
  category_label: string;
  matched_rule: string;
  rule_description: string;
  locator: string | null;
  /** Hostile page content. Render as text only, never as markup. */
  evidence_text: string;
  /** Set when the text was decoded or reassembled first, e.g. "base64". */
  obfuscation?: string | null;
  /** Human label for the transform, e.g. "Base64, then ROT13". */
  obfuscation_label?: string | null;
  risk_weight: number;
  impact: string | null;
  remediation: string | null;
}

export interface ScanSummary {
  id: string;
  source_kind: ScanSourceKind;
  target_url: string | null;
  target_filename: string | null;
  score: number;
  severity: SeverityInfo;
  finding_count: number;
  created_at: string;
}

export interface ExtractionSummary {
  sources: Record<string, number>;
  segments: number;
  truncated: boolean;
}

export interface ScanResult extends ScanSummary {
  findings: Finding[];
  extraction_summary: ExtractionSummary | null;
  limitations: string[];
}

export interface DemoPage {
  id: string;
  title: string;
  technique: string;
  description: string;
  expected_findings: number;
  expected_severity: Severity;
}

// --------------------------------------------------------------------------
// ShadowPrompt Lab (mirrors app/schemas/lab.py)
// --------------------------------------------------------------------------

export type LlmProvider = "openai_compatible" | "anthropic" | "gemini" | "azure_openai";

export type Rating = "secure" | "moderate" | "vulnerable" | "critical";

export interface ConnectionTestResult {
  session_id: string;
  provider: LlmProvider;
  model_name: string;
  endpoint_host: string;
  latency_ms: number;
  reply_preview: string;
}

export interface CampaignStarted {
  campaign_id: string;
  status: CampaignStatus;
  total_tests: number;
}

export interface RatingInfo {
  level: Rating;
  label: string;
  interpretation: string;
  recommendation: string;
}

export interface LevelScore {
  level: number;
  name: string;
  total: number;
  passed: number;
  partial: number;
  failed: number;
  unclear: number;
  score: number | null;
}

export interface EvaluationLayer {
  verdict: Verdict | null;
  reasons: string[];
}

export interface PageScanSummary {
  score: number;
  severity: Severity;
  sources: string[];
  categories: string[];
  /** Encodings ShadowScan undid to find the instruction, e.g. ["base64"]. */
  decoded?: string[];
}

export interface JudgeOutcome {
  verdict: Verdict | null;
  reason: string;
  model: string | null;
  cached: boolean;
}

export interface EvaluationDetail {
  decided_by: string;
  layer1?: EvaluationLayer;
  layer2?: EvaluationLayer;
  layer3?: JudgeOutcome;
  turns?: Array<{ turn: number; verdict: Verdict | null; reasons: string[] }>;
  page_scan?: PageScanSummary;
  error?: { code: string; message: string };
}

export type ReportFormat = "html" | "pdf";

/** Events on the campaign stream (GET /lab/campaigns/{id}/stream). */
export type CampaignEvent =
  | { type: "snapshot"; campaign: Campaign }
  | { type: "result"; result: TestResult }
  | { type: "status"; status: CampaignStatus }
  | { type: "done"; status: CampaignStatus; overall_score?: number | null; error?: string | null }
  | { type: "resync" };

export interface TestResult {
  id: string;
  payload_id: string;
  level: number;
  category: string;
  technique: string;
  name: string;
  description: string;
  objective: string;
  language?: string;
  language_name?: string;
  /** Attack text, shown only after the test ran. Render as text. */
  attack_text: string;
  verdict: Verdict;
  /** Trimmed model reply. Untrusted: render as text only. */
  response_summary: string | null;
  evaluation_detail: EvaluationDetail | null;
  latency_ms: number | null;
  created_at: string;
}

export interface CampaignSummary {
  id: string;
  session: { id: string; provider: string; model_name: string; endpoint_host: string | null };
  levels_run: number[];
  status: CampaignStatus;
  total_tests: number;
  completed_tests: number;
  overall_score: number | null;
  rating: RatingInfo | null;
  started_at: string;
  completed_at: string | null;
}

export interface Campaign extends CampaignSummary {
  config: { sample_size: number | null; timeout_seconds: number; max_retries: number } | null;
  error_message: string | null;
  current_level: number | null;
  level_scores: LevelScore[];
  results: TestResult[];
}

export interface LevelSummary {
  level: number;
  name: string;
  category: string;
  danger: string;
  test_count: number;
  available: boolean;
}

/** What this deployment allows. */
export interface LabCapabilities {
  /** True only on self-hosted deployments with LLM_ALLOW_PRIVATE_ENDPOINTS set. */
  local_endpoints_allowed: boolean;
  judge_enabled: boolean;
}

/** An opt-in pack of tests written in one language other than English. */
export interface LanguagePackSummary {
  code: string;
  name: string;
  test_count: number;
  /** Tests in the pack at each level, keyed by level number. */
  level_counts: Record<string, number>;
}

export interface PayloadLibrarySummary {
  version: number;
  /** English tests, which every campaign runs. */
  total_tests: number;
  levels: LevelSummary[];
  languages?: LanguagePackSummary[];
}
