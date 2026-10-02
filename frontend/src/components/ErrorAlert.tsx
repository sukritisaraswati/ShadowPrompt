import type { ApiError, ErrorCode } from "@/api/types";

/** Plain-language guidance per failure, so users know what to do next. */
const GUIDANCE: Partial<Record<ErrorCode, string>> = {
  BLOCKED_TARGET:
    "Only public internet addresses can be reached. Private networks, localhost, and cloud metadata services are refused to protect the server.",
  FETCH_FAILED: "The page could not be retrieved. Check the address, or upload the HTML file instead.",
  FETCH_TIMEOUT: "The site took too long to respond. Try again, or upload the HTML file instead.",
  RESPONSE_TOO_LARGE: "The page is over the 5 MB scan limit.",
  UPLOAD_TOO_LARGE: "The file is over the 2 MB upload limit.",
  UNSUPPORTED_FILE_TYPE: "Only HTML pages can be scanned.",
  RATE_LIMITED: "You have made a lot of requests in a short time. Wait and try again.",
  NETWORK_ERROR: "Check that the ShadowPrompt backend is running.",
  NOT_FOUND: "It may have been deleted, or the link may be wrong.",
  CONFLICT: "Wait for the campaign to finish, or stop it first.",
  LLM_AUTH_FAILED: "Check that the API key is correct, active, and belongs to this provider.",
  LLM_MODEL_NOT_FOUND: "Check the base URL and the exact model name your provider expects.",
  LLM_RATE_LIMITED: "Your provider is limiting requests. Wait a little, or raise your plan's limits.",
  LLM_TIMEOUT: "The model took too long to answer. Try again, or raise the timeout.",
  LLM_UNREACHABLE: "Check the base URL and that the provider is online.",
};

export default function ErrorAlert({ error, title }: { error: ApiError; title?: string }) {
  const guidance = GUIDANCE[error.code];
  return (
    <div
      role="alert"
      className="rounded-md border border-rose-300 bg-rose-50 px-4 py-3 text-sm text-rose-900 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-100"
    >
      <p className="font-semibold">{title ?? error.message}</p>
      {title && <p className="mt-1">{error.message}</p>}
      {error.detail && <p className="mt-1 opacity-80">Detail: {error.detail}</p>}
      {guidance && <p className="mt-1">{guidance}</p>}
    </div>
  );
}
