/**
 * Routing contract -- blueprint section 8.
 *
 * Every documented route must resolve to a real page, and the two service
 * groups must both be reachable from the persistent navigation.
 */

import { screen, waitFor } from "@testing-library/react";
import axios from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "@/App";
import { http } from "@/api/client";
import { renderWithProviders } from "@/test/utils";

// Home probes /health on mount. The default is a promise that never settles,
// so route tests never trigger a state update outside act(). The two status
// tests below install their own resolved or rejected mock.
beforeEach(() => {
  vi.spyOn(axios, "get").mockReturnValue(new Promise(() => {}));
  // Pages that load data stay in their loading state for routing tests.
  vi.spyOn(http, "get").mockReturnValue(new Promise(() => {}));
});

const ROUTES: Array<[path: string, heading: RegExp]> = [
  ["/", /shadowprompt/i],
  ["/lab/connect", /connect a target/i],
  ["/lab/configure", /campaign setup/i],
  ["/lab/running", /live test run/i],
  ["/lab/history", /past campaigns/i],
  ["/lab/compare", /model comparison/i],
  ["/scan", /shadowscan/i],
  ["/scan/demo", /demo lab/i],
  ["/scan/history", /scan history/i],
  ["/about", /methodology and limitations/i],
];

describe("routing", () => {
  it.each(ROUTES)("renders %s", async (path, heading) => {
    renderWithProviders(<App />, { route: path });
    expect(
      await screen.findByRole("heading", { level: 1, name: heading }),
    ).toBeInTheDocument();
  });

  it("shows a loading state while a scan result is fetched", async () => {
    renderWithProviders(<App />, { route: "/scan/results/abc123" });
    expect(await screen.findByRole("status")).toHaveTextContent(/loading scan/i);
  });

  it("shows a not-found page for an unknown route", async () => {
    renderWithProviders(<App />, { route: "/nope/does-not-exist" });
    expect(
      await screen.findByRole("heading", { level: 1, name: /page not found/i }),
    ).toBeInTheDocument();
  });

  it("renders both service groups in the persistent navigation", () => {
    renderWithProviders(<App />, { route: "/" });
    const nav = screen.getByRole("navigation", { name: /main/i });

    expect(nav).toHaveTextContent(/lab/i);
    expect(nav).toHaveTextContent(/shadowscan/i);
  });

  it("always shows the defensive-use notice", () => {
    renderWithProviders(<App />, { route: "/scan" });
    expect(
      screen.getByText(/for authorized, educational, and defensive security research only/i),
    ).toBeInTheDocument();
  });
});

describe("home backend status", () => {
  it("surfaces an unreachable backend instead of failing silently", async () => {
    vi.spyOn(axios, "get").mockRejectedValue(new Error("offline in tests"));

    renderWithProviders(<App />, { route: "/" });
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(/backend unreachable/i),
    );
  });

  it("reports a healthy backend", async () => {
    vi.spyOn(axios, "get").mockResolvedValue({
      data: {
        status: "ok",
        version: "0.1.0",
        environment: "test",
        uptime_seconds: 1,
        database: "ok",
        timestamp: new Date().toISOString(),
      },
    });

    renderWithProviders(<App />, { route: "/" });
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/backend ok/i));
  });
});
