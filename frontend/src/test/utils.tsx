import { render, type RenderOptions, type RenderResult } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";

import { SessionProvider } from "@/context/SessionContext";
import { ThemeProvider } from "@/context/ThemeContext";

interface Options extends Omit<RenderOptions, "wrapper"> {
  /** Initial history entries for the in-memory router. */
  route?: string;
}

/** Render a component inside the same provider stack the real app uses. */
export function renderWithProviders(
  ui: ReactElement,
  { route = "/", ...options }: Options = {},
): RenderResult {
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <ThemeProvider>
        <SessionProvider>
          <MemoryRouter
            initialEntries={[route]}
            future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
          >
            {children}
          </MemoryRouter>
        </SessionProvider>
      </ThemeProvider>
    );
  }

  return render(ui, { wrapper: Wrapper, ...options });
}

/** Every key present across the browser storage mechanisms. */
export function allStoredValues(): string {
  const parts: string[] = [];
  for (const storage of [window.localStorage, window.sessionStorage]) {
    for (let i = 0; i < storage.length; i += 1) {
      const key = storage.key(i);
      if (key === null) continue;
      parts.push(key, storage.getItem(key) ?? "");
    }
  }
  return parts.join("\u0000");
}
