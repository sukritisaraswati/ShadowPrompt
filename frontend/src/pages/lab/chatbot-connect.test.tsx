/**
 * Connecting the user's own chatbot: the form, the canary kit, and what is sent.
 */

import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as labApi from "@/api/lab";
import Connect from "@/pages/lab/Connect";
import { renderWithProviders } from "@/test/utils";

const TOKEN = "Bearer bot-secret-TOKEN-0123456789";

beforeEach(() => {
  vi.spyOn(labApi, "getCapabilities").mockResolvedValue({ local_endpoints_allowed: false, judge_enabled: false });
});

async function openChatbotForm() {
  renderWithProviders(<Connect />);
  await userEvent.click(screen.getByText("My chatbot"));
}

describe("validateChatbot", () => {
  const base = { bodyTemplate: '{"m": "{{message}}"}', responsePath: "reply", mode: "message" as const, headers: [] };

  it("accepts a usable template and explains unusable ones", () => {
    expect(labApi.validateChatbot(base)).toBeNull();
    expect(labApi.validateChatbot({ ...base, bodyTemplate: '{"m": "hi"}' })).toMatch(/\{\{message\}\}/);
    expect(labApi.validateChatbot({ ...base, bodyTemplate: "{m: {{message}}}" })).toMatch(/valid JSON/);
    expect(labApi.validateChatbot({ ...base, mode: "server" })).toMatch(/conversation_id/);
    expect(labApi.validateChatbot({ ...base, mode: "history" })).toMatch(/history/);
    expect(labApi.validateChatbot({ ...base, headers: [{ name: "Bad Header", value: "x" }] })).toMatch(/header name/);
  });

  it("generates canaries in the server's format", () => {
    for (let i = 0; i < 20; i++) expect(labApi.generateCanary()).toMatch(/^[A-Z]{4,12}-\d{4}$/);
  });
});

describe("Connect: my chatbot", () => {
  it("offers the starting template for each conversation mode", async () => {
    await openChatbotForm();
    const template = screen.getByLabelText(/request body/i);
    expect(template).toHaveValue(labApi.TEMPLATES.history);
    await userEvent.click(screen.getByLabelText(/my server keeps the conversation/i));
    expect(template).toHaveValue(labApi.TEMPLATES.server);
  });

  it("shows a canary snippet to plant, and keeps header values hidden", async () => {
    await openChatbotForm();
    const snippet = screen.getByTestId("canary-snippet").textContent ?? "";
    expect(snippet).toMatch(/^Confidential internal access code: [A-Z]{4,12}-\d{4}\./);
    expect(screen.getByLabelText("Header 1 value")).toHaveAttribute("type", "password");
  });

  it("sends the chatbot settings, with the canary only once it is planted", async () => {
    const spy = vi.spyOn(labApi, "testConnection").mockResolvedValue({
      session_id: "session-bot",
      provider: "chatbot",
      model_name: "Helpdesk bot",
      endpoint_host: "bot.example.com",
      latency_ms: 80,
      reply_preview: "OK",
    });
    await openChatbotForm();
    const name = screen.getByLabelText(/chatbot name/i);
    await userEvent.clear(name);
    await userEvent.type(name, "Helpdesk bot");
    await userEvent.type(screen.getByLabelText(/chat endpoint url/i), "https://bot.example.com/api/chat");
    await userEvent.type(screen.getByLabelText("Header 1 value"), TOKEN);
    await userEvent.click(screen.getByRole("button", { name: /test connection/i }));

    expect(await screen.findByText(/connected to helpdesk bot/i)).toBeInTheDocument();
    const sent = spy.mock.calls[0][0];
    expect(sent).toMatchObject({ provider: "chatbot", baseUrl: "https://bot.example.com/api/chat", modelName: "Helpdesk bot" });
    expect(sent.chatbot?.headers).toEqual([{ name: "Authorization", value: TOKEN }]);
    expect(sent.chatbot?.canary).toBeUndefined();
    expect(document.body.innerHTML).not.toContain(TOKEN);

    await userEvent.click(screen.getByLabelText(/added it to my chatbot's instructions/i));
    await userEvent.click(screen.getByRole("button", { name: /test connection/i }));
    await vi.waitFor(() => expect(spy).toHaveBeenCalledTimes(2));
    const planted = spy.mock.calls[1][0].chatbot?.canary;
    expect(screen.getByTestId("canary-snippet").textContent).toContain(planted);
  });

  it("refuses a broken template before contacting anything", async () => {
    const spy = vi.spyOn(labApi, "testConnection");
    await openChatbotForm();
    await userEvent.type(screen.getByLabelText(/chat endpoint url/i), "https://bot.example.com/chat");
    const template = screen.getByLabelText(/request body/i);
    await userEvent.clear(template);
    await userEvent.type(template, "not json");
    await userEvent.click(screen.getByRole("button", { name: /test connection/i }));
    expect(screen.getByRole("alert")).toHaveTextContent(/\{\{message\}\}|valid JSON/);
    expect(spy).not.toHaveBeenCalled();
  });
});
