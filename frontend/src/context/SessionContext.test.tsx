/**
 * Security tests for session handling.
 *
 * Blueprint 10.1: the API key is held in React state and nowhere else. These
 * tests fail the moment someone persists it.
 */

import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import {
  SessionProvider,
  describeConnection,
  useSession,
  type LlmConnection,
} from "@/context/SessionContext";
import { allStoredValues } from "@/test/utils";

const SECRET = "sk-proj-TESTKEY0123456789abcdefghijklmnop";

const CONNECTION: LlmConnection = {
  provider: "openai_compatible",
  baseUrl: "https://api.openai.com/v1",
  modelName: "gpt-4o-mini",
  apiKey: SECRET,
};

function wrapper({ children }: { children: ReactNode }) {
  return <SessionProvider>{children}</SessionProvider>;
}

describe("SessionProvider", () => {
  it("starts with no connection", () => {
    const { result } = renderHook(() => useSession(), { wrapper });
    expect(result.current.connection).toBeNull();
    expect(result.current.isVerified).toBe(false);
    expect(result.current.sessionId).toBeNull();
  });

  it("holds a verified connection in memory", () => {
    const { result } = renderHook(() => useSession(), { wrapper });

    act(() => result.current.setVerifiedConnection(CONNECTION, "session-1"));

    expect(result.current.connection?.apiKey).toBe(SECRET);
    expect(result.current.isVerified).toBe(true);
    expect(result.current.sessionId).toBe("session-1");
  });

  it("marks a newly set connection as unverified until it is probed", () => {
    const { result } = renderHook(() => useSession(), { wrapper });

    act(() => result.current.setVerifiedConnection(CONNECTION, "session-1"));
    act(() => result.current.setConnection({ ...CONNECTION, modelName: "gpt-4o" }));

    expect(result.current.isVerified).toBe(false);
  });

  it("forgets the key when the session is cleared", () => {
    const { result } = renderHook(() => useSession(), { wrapper });

    act(() => result.current.setVerifiedConnection(CONNECTION, "session-1"));
    act(() => result.current.clearSession());

    expect(result.current.connection).toBeNull();
    expect(result.current.isVerified).toBe(false);
  });

  it("never writes the API key to browser storage", () => {
    const { result } = renderHook(() => useSession(), { wrapper });

    act(() => result.current.setVerifiedConnection(CONNECTION, "session-1"));

    expect(allStoredValues()).not.toContain(SECRET);
  });

  it("drops the key when the provider unmounts", () => {
    const { result, unmount } = renderHook(() => useSession(), { wrapper });

    act(() => result.current.setVerifiedConnection(CONNECTION, "session-1"));
    unmount();

    expect(allStoredValues()).not.toContain(SECRET);
  });

  it("throws when used outside a provider", () => {
    expect(() => renderHook(() => useSession())).toThrow(/within a SessionProvider/);
  });
});

describe("describeConnection", () => {
  it("reports not connected when there is no connection", () => {
    expect(describeConnection(null)).toBe("Not connected");
  });

  it("never includes any part of the key", () => {
    const summary = describeConnection(CONNECTION);
    expect(summary).not.toContain(SECRET);
    expect(summary).not.toContain(SECRET.slice(0, 8));
    expect(summary).toContain("key supplied");
  });

  it("distinguishes an endpoint used without a key", () => {
    const local: LlmConnection = {
      provider: "openai_compatible",
      baseUrl: "http://localhost:11434/v1",
      modelName: "llama3",
    };
    expect(describeConnection(local)).toBe("llama3 at localhost:11434 (no key)");
  });
});
