import { describe, expect, it } from "vitest";
import running from "./fixtures/running.json";
import { parseRuntimeStatus } from "./model";
import { renderDashboard, renderLogs } from "./render";

describe("renderDashboard", () => {
  it("renders status text without interpreting markup", () => {
    const data = structuredClone(running);
    data.tailscale.Self.HostName = '<img src=x onerror="alert(1)">';
    data.tailscale.Self.DNSName = '<img src=x onerror="alert(1)">';
    const root = document.createElement("div");

    renderDashboard(root, parseRuntimeStatus(JSON.stringify(data)));

    expect(root.querySelector("img")).toBeNull();
    expect(root.textContent).toContain('<img src=x onerror="alert(1)">');
  });

  it("exposes an enable-disable control based on current state", () => {
    const root = document.createElement("div");

    renderDashboard(root, parseRuntimeStatus(JSON.stringify(running)));

    expect(root.querySelector<HTMLButtonElement>("[data-action=disable]")?.textContent).toContain(
      "禁用",
    );
    expect(root.querySelector("[data-action=open-panel]")).not.toBeNull();
  });
});

describe("renderLogs", () => {
  it("renders logs as text", () => {
    const root = document.createElement("div");

    renderLogs(root, "<script>bad()</script>");

    expect(root.querySelector("script")).toBeNull();
    expect(root.textContent).toContain("<script>bad()</script>");
  });
});
