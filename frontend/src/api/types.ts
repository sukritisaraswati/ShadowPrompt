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

export type Track = "direct" | "indirect";

export interface AttackLevel {
  /** Level code, e.g. "D1" or "I5". */
  code: string;
  name: string;
  danger: string;
}

/** The two attack tracks of five levels each (mirrors LEVELS in payloads.py). */
export const ATTACK_TRACKS: ReadonlyArray<{
  track: Track;
  name: string;
  summary: string;
  levels: ReadonlyArray<AttackLevel>;
}> = [
  {
    track: "direct",
    name: "Direct prompt injection",
    summary: "The attacker is the user, typing straight at the model.",
    levels: [
      { code: "D1", name: "Basic Jailbreak", danger: "Low" },
      { code: "D2", name: "Persona & Role Manipulation", danger: "Medium" },
      { code: "D3", name: "Adversarial Instruction Design", danger: "High" },
      { code: "D4", name: "Multi-turn Escalation", danger: "Very High" },
      { code: "D5", name: "Combined & Advanced Attacks", danger: "Critical" },
    ],
  },
  {
    track: "indirect",
    name: "Indirect prompt injection",
    summary: "The attacker hides instructions in content the model reads.",
    levels: [
      { code: "I1", name: "Hidden Page Instructions", danger: "Medium" },
      { code: "I2", name: "Disguised Placement", danger: "High" },
      { code: "I3", name: "Obfuscated Instructions", danger: "High" },
      { code: "I4", name: "Multi-Vector Pages", danger: "Very High" },
      { code: "I5", name: "Chained Indirect Attacks", danger: "Critical" },
    ],
  },
];

/** Every level code in display order: D1 to D5, then I1 to I5. */
export const LEVEL_ORDER: ReadonlyArray<string> = ATTACK_TRACKS.flatMap((t) => t.levels.map((l) => l.code));

export const LEVEL_NAMES: Readonly<Record<string, string>> = Object.fromEntries(
  ATTACK_TRACKS.flatMap((t) => t.levels.map((l) => [l.code, l.name])),
);

export function compareLevelCodes(a: string, b: string): number {
  return LEVEL_ORDER.indexOf(a) - LEVEL_ORDER.indexOf(b);
}

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
  /** How the finding was recovered, as a sentence, e.g. "Decoded from Base64". */
  obfuscation_note?: string | null;
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

/** Present when the page's JavaScript was run before scanning. */
export interface RenderSummary {
  requests: number;
  blocked: number;
  truncated: boolean;
  error: string | null;
  segments?: number;
  added_findings?: number;
}

export interface ExtractionSummary {
  sources: Record<string, number>;
  segments: number;
  truncated: boolean;
  rendered?: RenderSummary;
}

export interface ScanCapabilities {
  render_available: boolean;
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
  code: string;
  track: Track;
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
  track: Track;
  /** Level code, e.g. "D3". */
  code: string;
  level: number;
  category: string;
  technique: string;
  name: string;
  description: string;
  objective: string;
  language?: string;
  language_name?: string;
  /** Name of the uploaded pack this test came from, if any. */
  custom_pack?: string | null;
  /** Attack text, shown only after the test ran. Render as text. */
  attack_text: string;
  verdict: Verdict;
  /** Trimmed model reply. Untrusted: render as text only. */
  response_summary: string | null;
  evaluation_detail: EvaluationDetail | null;
  latency_ms: number | null;
  created_at: string;
}

export interface TrackScore {
  track: Track;
  name: string;
  score: number | null;
  rating: RatingInfo | null;
}

export interface CampaignSummary {
  id: string;
  session: { id: string; provider: string; model_name: string; endpoint_host: string | null };
  /** Level codes run, e.g. ["D1", "I2"]. */
  levels_run: string[];
  status: CampaignStatus;
  total_tests: number;
  completed_tests: number;
  overall_score: number | null;
  rating: RatingInfo | null;
  /** Score in each track that was run. */
  track_scores?: TrackScore[];
  started_at: string;
  completed_at: string | null;
}

export interface Campaign extends CampaignSummary {
  config: { sample_size: number | null; timeout_seconds: number; max_retries: number } | null;
  error_message: string | null;
  /** Level code being run, e.g. "D2". */
  current_level: string | null;
  level_scores: LevelScore[];
  results: TestResult[];
}

export interface LevelSummary {
  code: string;
  track: Track;
  level: number;
  name: string;
  description: string;
  category: string;
  danger: string;
  test_count: number;
  available: boolean;
}

/** A test inside an uploaded custom pack. */
export interface PackTest {
  id: string;
  code: string;
  track: Track;
  level: number;
  name: string;
  objective: string;
  language: string;
}

/** An uploaded custom test pack. Name and tests are user content: render as text. */
export interface PayloadPackSummary {
  id: string;
  name: string;
  description: string | null;
  test_count: number;
  /** Tests at each level, keyed by level code. */
  level_counts: Record<string, number>;
  created_at: string;
}

export interface PayloadPack extends PayloadPackSummary {
  tests: PackTest[];
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
  /** Tests in the pack at each level, keyed by level code. */
  level_counts: Record<string, number>;
}

export interface PayloadLibrarySummary {
  version: number;
  /** English tests, which every campaign runs. */
  total_tests: number;
  tracks?: { track: Track; name: string; test_count: number }[];
  levels: LevelSummary[];
  languages?: LanguagePackSummary[];
}
