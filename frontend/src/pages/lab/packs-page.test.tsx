/**
 * Custom tests page: client-side checks, upload, listing, and deletion.
 */

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import * as labApi from "@/api/lab";
import type { PayloadPack, PayloadPackSummary } from "@/api/types";
import Packs from "@/pages/lab/Packs";
import { renderWithProviders } from "@/test/utils";

const SUMMARY: PayloadPackSummary = {
  id: "pack-1",
  name: "Helpdesk tests",
  description: "Regression tests for the helpdesk bot.",
  test_count: 2,
  level_counts: { "1": 1, "4": 1 },
  created_at: "2026-10-02T10:00:00Z",
};

const PACK: PayloadPack = {
  ...SUMMARY,
  tests: [
    { id: "C1-ABCDEF-001", level: 1, name: "Override code request", objective: "secret", language: "en" },
    { id: "C4-ABCDEF-002", level: 4, name: "<img src=x onerror=alert(1)> page", objective: "injection", language: "es" },
  ],
};

function packFile(name = "pack.json", body = '{"format":"shadowprompt-pack/1"}') {
  return new File([body], name, { type: "application/json" });
}

describe("validatePackFile", () => {
  it("accepts a JSON file and rejects the rest", () => {
    expect(labApi.validatePackFile(null)).toMatch(/choose/i);
    expect(labApi.validatePackFile(packFile("pack.txt"))).toMatch(/\.json/);
    expect(labApi.validatePackFile(packFile("pack.json", ""))).toMatch(/empty/);
    const big = new File([new Uint8Array(labApi.MAX_PACK_BYTES + 1)], "big.json");
    expect(labApi.validatePackFile(big)).toMatch(/256 KB/);
    expect(labApi.validatePackFile(packFile("Pack.JSON"))).toBeNull();
  });
});

describe("Packs", () => {
  it("lists packs and shows a pack's tests as text", async () => {
    vi.spyOn(labApi, "listPacks").mockResolvedValue([SUMMARY]);
    vi.spyOn(labApi, "getPack").mockResolvedValue(PACK);
    const { container } = renderWithProviders(<Packs />);

    expect(await screen.findByText("Helpdesk tests")).toBeInTheDocument();
    expect(screen.getByText(/2 tests · L1×1 · L4×1/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /show tests/i }));
    expect(await screen.findByText("Override code request")).toBeInTheDocument();
    expect(screen.getByText("<img src=x onerror=alert(1)> page")).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });

  it("refuses a non-JSON file without uploading", async () => {
    vi.spyOn(labApi, "listPacks").mockResolvedValue([]);
    const upload = vi.spyOn(labApi, "uploadPack");
    renderWithProviders(<Packs />);

    await userEvent.upload(screen.getByLabelText(/pack file/i), packFile("notes.txt"));
    await userEvent.click(screen.getByRole("button", { name: /upload pack/i }));
    expect(screen.getByRole("alert")).toHaveTextContent(/\.json/);
    expect(upload).not.toHaveBeenCalled();
  });

  it("uploads a pack and refreshes the list", async () => {
    const list = vi.spyOn(labApi, "listPacks").mockResolvedValueOnce([]).mockResolvedValueOnce([SUMMARY]);
    const upload = vi.spyOn(labApi, "uploadPack").mockResolvedValue(PACK);
    renderWithProviders(<Packs />);

    expect(await screen.findByText(/no packs yet/i)).toBeInTheDocument();
    const file = packFile();
    await userEvent.upload(screen.getByLabelText(/pack file/i), file);
    await userEvent.click(screen.getByRole("button", { name: /upload pack/i }));

    expect(await screen.findByRole("status")).toHaveTextContent(/2 tests checked and ready/);
    expect(upload).toHaveBeenCalledWith(file);
    expect(await screen.findByText("Helpdesk tests")).toBeInTheDocument();
    expect(list).toHaveBeenCalledTimes(2);
  });

  it("explains why the server rejected a pack", async () => {
    vi.spyOn(labApi, "listPacks").mockResolvedValue([]);
    vi.spyOn(labApi, "uploadPack").mockRejectedValue({
      code: "VALIDATION_ERROR",
      message: "A test in the pack is not valid.",
      detail: "test 1 (Override): protected value appears in the attack text",
    });
    renderWithProviders(<Packs />);

    await userEvent.upload(screen.getByLabelText(/pack file/i), packFile());
    await userEvent.click(screen.getByRole("button", { name: /upload pack/i }));
    const alert = await screen.findByText(/a test in the pack is not valid/i);
    expect(alert.closest("[role=alert]") ?? alert).toBeInTheDocument();
  });

  it("deletes a pack after confirmation", async () => {
    vi.spyOn(labApi, "listPacks").mockResolvedValueOnce([SUMMARY]).mockResolvedValueOnce([]);
    const remove = vi.spyOn(labApi, "deletePack").mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderWithProviders(<Packs />);

    await userEvent.click(await screen.findByRole("button", { name: /delete/i }));
    expect(remove).toHaveBeenCalledWith("pack-1");
    await waitFor(() => expect(screen.getByText(/no packs yet/i)).toBeInTheDocument());
  });
});
