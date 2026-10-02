/**
 * Error normalisation in the API client.
 *
 * Pages switch on `code` to render a specific message per failure mode, so
 * every path out of the client has to produce that shape.
 */

import { AxiosError, AxiosHeaders } from "axios";
import { describe, expect, it } from "vitest";

import { toApiError } from "@/api/client";
import type { ApiError } from "@/api/types";

function axiosErrorWithStatus(status: number, data?: unknown): AxiosError {
  const config = { headers: new AxiosHeaders() };
  const error = new AxiosError("request failed", "ERR_BAD_RESPONSE", config as never);
  error.response = {
    status,
    statusText: "",
    data,
    headers: {},
    config: config as never,
  };
  return error;
}

describe("toApiError", () => {
  it("passes through a backend error envelope untouched", () => {
    const envelope: ApiError = {
      code: "BLOCKED_TARGET",
      message: "Target address is not permitted",
      detail: "loopback",
    };

    expect(toApiError(axiosErrorWithStatus(400, envelope))).toEqual(envelope);
  });

  it.each([
    [404, "NOT_FOUND"],
    [429, "RATE_LIMITED"],
    [501, "NOT_IMPLEMENTED"],
    [422, "VALIDATION_ERROR"],
    [500, "INTERNAL_ERROR"],
    [418, "INTERNAL_ERROR"],
  ])("maps bare status %i to %s", (status, expected) => {
    expect(toApiError(axiosErrorWithStatus(status)).code).toBe(expected);
  });

  it("reports a network error when no response arrived", () => {
    const config = { headers: new AxiosHeaders() };
    const error = new AxiosError("connect refused", "ECONNREFUSED", config as never);

    const result = toApiError(error);
    expect(result.code).toBe("NETWORK_ERROR");
    expect(result.message).toMatch(/could not reach/i);
  });

  it("handles a value that is not an Axios error at all", () => {
    expect(toApiError(new Error("boom")).code).toBe("INTERNAL_ERROR");
    expect(toApiError("boom").code).toBe("INTERNAL_ERROR");
    expect(toApiError(null).code).toBe("INTERNAL_ERROR");
  });

  it("is idempotent for an already-normalised error", () => {
    const normalised: ApiError = { code: "LLM_AUTH_FAILED", message: "bad key" };
    expect(toApiError(normalised)).toEqual(normalised);
  });

  it("ignores a response body that is not an error envelope", () => {
    const result = toApiError(axiosErrorWithStatus(500, "<html>gateway error</html>"));
    expect(result.code).toBe("INTERNAL_ERROR");
    expect(result.message).toContain("500");
  });
});
