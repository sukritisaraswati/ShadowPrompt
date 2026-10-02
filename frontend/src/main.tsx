import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "@/App";
import { SessionProvider } from "@/context/SessionContext";
import { ThemeProvider } from "@/context/ThemeContext";

import "@/index.css";

const container = document.getElementById("root");
if (!container) {
  throw new Error("Root element #root is missing from index.html");
}

createRoot(container).render(
  <StrictMode>
    <ThemeProvider>
      <SessionProvider>
        {/* Opt in to v7 behaviour now so the upgrade is a no-op later. */}
        <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <App />
        </BrowserRouter>
      </SessionProvider>
    </ThemeProvider>
  </StrictMode>,
);
