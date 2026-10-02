/**
 * Phase 3 frontend: live streaming, pause and resume, Layer 3 and ShadowScan
 * notes, PDF export, campaign and scan history, and model comparison.
 */

import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as labApi from "@/api/lab";
import * as scanApi from "@/api/scan";
import type { Campaign, CampaignSummary, TestResult } from "@/api/types";
import Compare, { compareTests } from "@/pages/lab/Compare";
import History from "@/pages/lab/History";
import Results from "@/pages/lab/Results";
import Running from "@/pages/lab/Running";
import ScanHistory from "@/pages/scan/ScanHistory";
import { renderWithProviders } from "@/test/utils";

function result(overrides: Partial<TestResult> = {}): TestResult {
  return {
    id: crypto.randomUUID(),
    payload_id: "D1-001",
    track: "direct",
    code: "D1",
    level: 1,
    category: "basic_override",
    technique: "direct override",
    name: "Ignore previous instructions",
    description: "",
    objective: "secret",
    attack_text: "attack",
    verdict: "PASS",
    response_summary: "I can't help with that.",
    evaluation_detail: { decided_by: "layer1" },
    latency_ms: 50,
    created_at: "2026-10-02T10:00:00Z",
    ...overrides,
  };
}

function campaign(overrides: Partial<Campaign> = {}): Campaign {
  return {
    id: "camp-1",
    session: { id: "s", provider: "openai_compatible", model_name: "model-a", endpoint_host: "api.example" },
    levels_run: ["D1", "I1"],
    status: "running",
    total_tests: 10,
    completed_tests: 1,
    overall_score: 80,
    rating: { level: "moderate", label: "Moderate", interpretation: "Gaps.", recommendation: "Fix them." },
    started_at: "2026-10-02T10:00:00Z",
    completed_at: null,
    config: null,
    error_message: null,
    current_level: "D1",
    level_scores: [
      { code: "D1", track: "direct", level: 1, name: "Basic Jailbreak", total: 4, passed: 4, partial: 0, failed: 0, unclear: 0, score: 100 },
      { code: "I1", track: "indirect", level: 1, name: "Hidden Page Instructions", total: 6, passed: 3, partial: 0, failed: 3, unclear: 0, score: 50 },
    ],
    results: [result()],
    ...overrides,
  };
}

function renderAt(path: string, pattern: string, element: React.ReactElement) {
  return renderWithProviders(
    <Routes>
      <Route path={pattern} element={element} />
      <Route path="/lab/results/:id" element={<p>results page reached</p>} />
      <Route path="/lab/compare" element={<p>compare page reached</p>} />
    </Routes>,
    { route: path },
  );
}

// --------------------------------------------------------------------------
// A controllable EventSource, since jsdom has none
// --------------------------------------------------------------------------

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  listeners = new Map<string, (e: MessageEvent<string>) => void>();
  onerror: (() => void) | null = null;
  closed = false;
  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }
  addEventListener(type: string, fn: (e: MessageEvent<string>) => void) {
    this.listeners.set(type, fn);
  }
  close() {
    this.closed = true;
  }
  emit(type: string, payload: object) {
    act(() => this.listeners.get(type)?.({ data: JSON.stringify({ type, ...payload }) } as MessageEvent<string>));
  }
}

describe("Running with a live stream", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("renders the snapshot, then live results, then opens the results page", async () => {
    const final = campaign({ status: "completed", completed_tests: 2 });
    vi.spyOn(labApi, "getCampaign").mockResolvedValue(final);
    renderAt("/lab/running?campaign=camp-1", "/lab/running", <Running />);

    const source = FakeEventSource.instances[0];
    expect(source.url).toBe("/api/v1/lab/campaigns/camp-1/stream");

    source.emit("snapshot", { campaign: campaign() });
    expect(await screen.findByText(/1 of 10 tests/i)).toBeInTheDocument();
    expect(screen.getByTestId("transport")).toHaveTextContent(/live/i);

    source.emit("result", { result: result({ verdict: "FAIL", name: "DAN", level: 2 }) });
    expect(screen.getByText(/2 of 10 tests/i)).toBeInTheDocument();
    expect(screen.getByText("DAN")).toBeInTheDocument();

    source.emit("done", { status: "completed" });
    expect(await screen.findByText(/results page reached/i)).toBeInTheDocument();
    expect(source.closed).toBe(true);
  });

  it("ignores a duplicated result event", async () => {
    renderAt("/lab/running?campaign=camp-1", "/lab/running", <Running />);
    const source = FakeEventSource.instances[0];
    const first = campaign();
    source.emit("snapshot", { campaign: first });
    source.emit("result", { result: first.results[0] });
    expect(await screen.findByText(/1 of 10 tests/i)).toBeInTheDocument();
  });

  it("falls back to polling when the stream fails", async () => {
    const poll = vi.spyOn(labApi, "getCampaign").mockResolvedValue(campaign());
    renderAt("/lab/running?campaign=camp-1", "/lab/running", <Running />);
    act(() => FakeEventSource.instances[0].onerror?.());
    await waitFor(() => expect(poll).toHaveBeenCalled());
    expect(await screen.findByTestId("transport")).toHaveTextContent(/refreshing/i);
  });

  it("pauses and resumes", async () => {
    const pause = vi.spyOn(labApi, "pauseCampaign").mockResolvedValue({});
    const resume = vi.spyOn(labApi, "resumeCampaign").mockResolvedValue({});
    renderAt("/lab/running?campaign=camp-1", "/lab/running", <Running />);
    const source = FakeEventSource.instances[0];
    source.emit("snapshot", { campaign: campaign() });

    await userEvent.click(await screen.findByRole("button", { name: /^pause$/i }));
    expect(pause).toHaveBeenCalledWith("camp-1");
    source.emit("status", { status: "paused" });

    await userEvent.click(await screen.findByRole("button", { name: /resume/i }));
    expect(resume).toHaveBeenCalledWith("camp-1");
    expect(screen.getByText(/paused/, { selector: "p" })).toBeInTheDocument();
  });
});

// --------------------------------------------------------------------------
// Results notes and PDF
// --------------------------------------------------------------------------

describe("Results for Phase 3 tests", () => {
  it("shows the ShadowScan rating and the Layer 3 ruling", async () => {
    vi.spyOn(labApi, "getCampaign").mockResolvedValue(
      campaign({
        status: "completed",
        results: [
          result({
            verdict: "FAIL",
            level: 4,
            name: "Comment override",
            evaluation_detail: {
              decided_by: "layer3",
              page_scan: { score: 42, severity: "medium", sources: ["html_comment"], categories: ["instruction_override"] },
              layer3: { verdict: "FAIL", reason: "It output the planted code.", model: "claude-sonnet-5-5", cached: false },
            },
          }),
        ],
      }),
    );
    renderAt("/lab/results/camp-1", "/lab/results/:id", <Results />);
    const notes = await screen.findByTestId("notes");
    expect(notes).toHaveTextContent(/ShadowScan rated this attack page medium \(42\/100\)/);
    expect(notes).toHaveTextContent(/html comment/);
    expect(notes).toHaveTextContent(/Layer 3 judge \(claude-sonnet-5-5\): It output the planted code/);
  });

  it("downloads the PDF report", async () => {
    vi.spyOn(labApi, "getCampaign").mockResolvedValue(campaign({ status: "completed" }));
    const download = vi.spyOn(labApi, "downloadCampaignReport").mockResolvedValue();
    renderAt("/lab/results/camp-1", "/lab/results/:id", <Results />);
    await userEvent.click(await screen.findByRole("button", { name: /download pdf report/i }));
    expect(download).toHaveBeenCalledWith("camp-1", "pdf");
  });
});

// --------------------------------------------------------------------------
// History pages
// --------------------------------------------------------------------------

function summary(id: string, model: string, score: number | null, status: Campaign["status"] = "completed"): CampaignSummary {
  const c = campaign({ id, overall_score: score, status });
  c.session = { ...c.session, model_name: model };
  return c;
}

describe("Campaign history", () => {
  it("lists campaigns and compares the selected ones", async () => {
    vi.spyOn(labApi, "listCampaigns").mockResolvedValue({
      items: [summary("a", "model-a", 80), summary("b", "model-b", 90), summary("c", "model-c", null, "failed")],
      pagination: { total: 3, limit: 20, offset: 0 },
    });
    renderAt("/lab/history", "/lab/history", <History />);

    const compare = await screen.findByRole("button", { name: /compare selected \(0\)/i });
    expect(compare).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: /model-c/i })).toBeDisabled();

    await userEvent.click(screen.getByRole("checkbox", { name: /model-a/i }));
    await userEvent.click(screen.getByRole("checkbox", { name: /model-b/i }));
    await userEvent.click(screen.getByRole("button", { name: /compare selected \(2\)/i }));
    expect(await screen.findByText(/compare page reached/i)).toBeInTheDocument();
  });

  it("filters by model and deletes after confirmation", async () => {
    const list = vi.spyOn(labApi, "listCampaigns").mockResolvedValue({
      items: [summary("a", "model-a", 80)],
      pagination: { total: 1, limit: 20, offset: 0 },
    });
    const remove = vi.spyOn(labApi, "deleteCampaign").mockResolvedValue({});
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderAt("/lab/history", "/lab/history", <History />);

    await userEvent.type(await screen.findByLabelText(/model/i, { selector: "input" }), "gpt");
    await waitFor(() => expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ model_name: "gpt" }), expect.anything()));

    await userEvent.click(screen.getByRole("button", { name: /delete/i }));
    expect(remove).toHaveBeenCalledWith("a");
  });
});

describe("Scan history", () => {
  it("lists scans and filters by severity", async () => {
    const list = vi.spyOn(scanApi, "listScans").mockResolvedValue({
      items: [
        {
          id: "scan-1",
          source_kind: "url",
          target_url: "https://example.com/page",
          target_filename: null,
          score: 72,
          severity: { level: "high", label: "High", meaning: "", recommended_action: "" },
          finding_count: 3,
          created_at: "2026-10-02T10:00:00Z",
        },
      ],
      pagination: { total: 1, limit: 20, offset: 0 },
    });
    renderAt("/scan/history", "/scan/history", <ScanHistory />);
    expect(await screen.findByText("https://example.com/page")).toBeInTheDocument();
    expect(screen.getByText("High")).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText(/severity/i), "critical");
    await waitFor(() => expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ severity: "critical" }), expect.anything()));
  });
});

// --------------------------------------------------------------------------
// Comparison
// --------------------------------------------------------------------------

describe("compareTests", () => {
  it("reports improvements and regressions relative to the first campaign", () => {
    const a = campaign({ results: [result({ payload_id: "D1-001", verdict: "FAIL" }), result({ payload_id: "D1-002", verdict: "PASS" }), result({ payload_id: "D1-003", verdict: "PASS" })] });
    const b = campaign({ results: [result({ payload_id: "D1-001", verdict: "PASS" }), result({ payload_id: "D1-002", verdict: "PARTIAL" }), result({ payload_id: "D1-003", verdict: "PASS" })] });
    const changes = compareTests([a, b]);
    expect(changes.map((c) => [c.payloadId, c.direction])).toEqual([
      ["D1-001", "improved"],
      ["D1-002", "regressed"],
    ]);
  });

  it("ignores unclear verdicts and tests only one campaign ran", () => {
    const a = campaign({ results: [result({ payload_id: "D1-001", verdict: "UNCLEAR" }), result({ payload_id: "D1-009" })] });
    const b = campaign({ results: [result({ payload_id: "D1-001", verdict: "FAIL" })] });
    expect(compareTests([a, b])).toEqual([]);
  });
});

describe("Compare page", () => {
  it("asks for campaigns when fewer than two are given", () => {
    renderAt("/lab/compare", "/lab/compare", <Compare />);
    expect(screen.getByRole("link", { name: /open campaign history/i })).toBeInTheDocument();
  });

  it("shows scores side by side with deltas", async () => {
    const a = campaign({ id: "a", overall_score: 60, results: [result({ payload_id: "D1-001", verdict: "FAIL" })] });
    a.session = { ...a.session, model_name: "model-v1" };
    const b = campaign({ id: "b", overall_score: 85, results: [result({ payload_id: "D1-001", verdict: "PASS" })] });
    b.session = { ...b.session, model_name: "model-v2" };
    vi.spyOn(labApi, "getCampaign").mockImplementation(async (id) => (id === "a" ? a : b));

    renderWithProviders(
      <Routes>
        <Route path="/lab/compare" element={<Compare />} />
      </Routes>,
      { route: "/lab/compare?ids=a,b" },
    );
    expect(await screen.findByRole("link", { name: "model-v1" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "model-v2" })).toBeInTheDocument();
    expect(screen.getByText("(+25)")).toBeInTheDocument();
    expect(screen.getByText(/1 test improved and 0 tests regressed/i)).toBeInTheDocument();
  });
});
