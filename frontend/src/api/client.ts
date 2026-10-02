/**
 * Shared Axios client.
 *
 * Two rules this module exists to enforce:
 *
 * 1. Every failure reaching a component is a normalised {@link ApiError}, so
 *    pages can switch on `code` instead of parsing Axios internals.
 * 2. Nothing credential-shaped is ever written to storage or to the console.
 *    An API key travels in a request body to our own backend and lives in
 *    React state for the lifetime of the tab, and nowhere else.
 */

import axios, {
  AxiosError,
  type AxiosInstance,
  type AxiosRequestConfig,
} from "axios";

import { ERROR_CODES, type ApiError, type ErrorCode, type HealthResponse } from "./types";

const KNOWN_CODES = new Set<string>(ERROR_CODES);

/** Relative base: Vite proxies to FastAPI in dev, same origin in production. */
export const API_BASE = "/api/v1";

export const http: AxiosInstance = axios.create({
  baseURL: API_BASE,
  timeout: 30_000,
  headers: { Accept: "application/json" },
});

function isApiError(value: unknown): value is ApiError {
  if (typeof value !== "object" || value === null) return false;
  // An AxiosError also has string `code` and `message` fields, so the code
  // must be one the backend actually emits.
  if (axios.isAxiosError(value)) return false;
  const candidate = value as ApiError;
  return (
    typeof candidate.code === "string" &&
    KNOWN_CODES.has(candidate.code) &&
    typeof candidate.message === "string"
  );
}

/** Convert anything Axios throws into the shared error shape. */
export function toApiError(error: unknown): ApiError {
  if (isApiError(error)) return error;

  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<unknown>;
    const body = axiosError.response?.data;

    if (isApiError(body)) return body;

    if (axiosError.response) {
      const status = axiosError.response.status;
      const code: ErrorCode =
        status === 404
          ? "NOT_FOUND"
          : status === 429
            ? "RATE_LIMITED"
            : status === 501
              ? "NOT_IMPLEMENTED"
              : status === 422
                ? "VALIDATION_ERROR"
                : "INTERNAL_ERROR";
      return { code, message: `Request failed with status ${status}` };
    }

    return {
      code: "NETWORK_ERROR",
      message: "Could not reach the ShadowPrompt backend.",
      detail: "Check that the API is running and reachable.",
    };
  }

  return { code: "INTERNAL_ERROR", message: "An unexpected error occurred." };
}

// Reject with the normalised shape so callers never handle raw Axios errors.
http.interceptors.response.use(
  (response) => response,
  (error: unknown) => Promise.reject(toApiError(error)),
);

/** GET helper returning the response body, throwing an {@link ApiError}. */
export async function get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const response = await http.get<T>(url, config);
  return response.data;
}

/** POST helper returning the response body, throwing an {@link ApiError}. */
export async function post<T>(
  url: string,
  data?: unknown,
  config?: AxiosRequestConfig,
): Promise<T> {
  const response = await http.post<T>(url, data, config);
  return response.data;
}

/** DELETE helper returning the response body, throwing an {@link ApiError}. */
export async function del<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const response = await http.delete<T>(url, config);
  return response.data;
}

/**
 * Platform health. Sits outside the version prefix, so it uses an absolute
 * path rather than the client baseURL.
 */
export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await axios.get<HealthResponse>("/health", { signal });
  return response.data;
}

/** A cancellation token for long-running scans and campaigns. */
export function createAbort(): AbortController {
  return new AbortController();
}
