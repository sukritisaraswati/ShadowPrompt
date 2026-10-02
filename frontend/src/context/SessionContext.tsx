/**
 * Holds the LLM connection for the current Lab session.
 *
 * SECURITY (blueprint 10.1): the API key lives in React state and nowhere
 * else. It is never written to localStorage, sessionStorage, IndexedDB, a
 * cookie, the URL, or the console. Closing the tab or reloading the page
 * destroys it, which is the intended behaviour -- the user reconnects.
 *
 * Any future change that persists `apiKey` breaks a documented guarantee and
 * an acceptance test.
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { ChatbotSettings, LlmProvider } from "@/api/types";

export interface LlmConnection {
  /** Wire format the backend uses to talk to the model (blueprint 3.1). */
  provider: LlmProvider;
  /** Endpoint base, e.g. https://api.openai.com/v1 */
  baseUrl: string;
  modelName: string;
  /** Absent for a local endpoint that needs no key. */
  apiKey?: string;
  /** Set when testing the user's own chatbot (provider "chatbot"). Memory only. */
  chatbot?: ChatbotSettings;
}

export interface SessionState {
  connection: LlmConnection | null;
  /** True once the backend connection probe has succeeded. */
  isVerified: boolean;
  sessionId: string | null;
}

export interface SessionContextValue extends SessionState {
  /** Record a connection that has passed the backend probe. */
  setVerifiedConnection: (connection: LlmConnection, sessionId: string) => void;
  /** Hold an unverified connection while the probe runs. */
  setConnection: (connection: LlmConnection | null) => void;
  /** Forget everything, including the key. */
  clearSession: () => void;
}

const EMPTY: SessionState = { connection: null, isVerified: false, sessionId: null };

const SessionContext = createContext<SessionContextValue | undefined>(undefined);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SessionState>(EMPTY);

  const setConnection = useCallback((connection: LlmConnection | null) => {
    setState((previous) => ({ ...previous, connection, isVerified: false }));
  }, []);

  const setVerifiedConnection = useCallback(
    (connection: LlmConnection, sessionId: string) => {
      setState({ connection, isVerified: true, sessionId });
    },
    [],
  );

  const clearSession = useCallback(() => setState(EMPTY), []);

  const value = useMemo<SessionContextValue>(
    () => ({ ...state, setConnection, setVerifiedConnection, clearSession }),
    [state, setConnection, setVerifiedConnection, clearSession],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (context === undefined) {
    throw new Error("useSession must be used within a SessionProvider");
  }
  return context;
}

/**
 * A connection summary that is safe to display or log. The key is reduced to
 * a presence flag -- not a masked prefix, which would still leak bytes.
 */
export function describeConnection(connection: LlmConnection | null): string {
  if (!connection) return "Not connected";
  let host = connection.baseUrl;
  try {
    host = new URL(connection.baseUrl).host;
  } catch {
    // Show the raw value if it is not a parseable URL.
  }
  if (connection.chatbot) {
    const canary = connection.chatbot.canary ? "canary planted" : "no canary";
    return `${connection.modelName}, your chatbot at ${host} (${canary})`;
  }
  const auth = connection.apiKey ? "key supplied" : "no key";
  return `${connection.modelName} at ${host} (${auth})`;
}
