import { describe, expect, it } from "vitest";
import running from "./fixtures/running.json";
import degraded from "./fixtures/degraded.json";
import migration from "./fixtures/migration-required.json";
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

describe("schema 2 dashboard", () => {
  it("shows module identity, real health and runtime generations", () => {
    const root = document.createElement("div");
    renderDashboard(root, parseRuntimeStatus(JSON.stringify(degraded)));
    expect(root.querySelector("h1")?.textContent).toBe("KernelSU-Tailscaled");
    expect(root.querySelector("[data-lifecycle=degraded]")?.textContent).toContain("降级");
    expect(root.querySelector('[data-state="unknown"]')?.textContent).toContain("未知");
    expect(root.textContent).toContain("DNS server is unreachable");
    expect(root.textContent).toContain("2.0.0-beta.2");
    expect(root.textContent).toContain("2.0.0-alpha.1");
    expect(root.querySelector("[data-action=apply-staged]")).not.toBeNull();
    expect(root.querySelector("[data-action=diagnostics]")).not.toBeNull();
  });

  it("exposes explicit migration without offering to start a duplicate identity", () => {
    const root = document.createElement("div");
    renderDashboard(root, parseRuntimeStatus(JSON.stringify(migration)));
    expect(root.querySelector("[data-action=migrate-legacy]")).not.toBeNull();
    expect(root.querySelector("[data-action=enable]")).toBeNull();
    expect(root.querySelector<HTMLButtonElement>("[data-action=restart]")?.disabled).toBe(true);
  });

  it("keeps migration available when lifecycle is the only migration signal", () => {
    const root = document.createElement("div");
    renderDashboard(root, parseRuntimeStatus(JSON.stringify({ ...migration, diagnostics: [] })));
    expect(root.querySelector("[data-action=migrate-legacy]")).not.toBeNull();
  });

  it("offers enable after migration even when the manager intent is enabled", () => {
    const root = document.createElement("div");
    const data = { ...migration, lifecycle: "stopped", diagnostics: [{ code: "migration-awaiting-enable", severity: "info", message: "Explicit enable required" }] };
    renderDashboard(root, parseRuntimeStatus(JSON.stringify(data)));
    expect(root.querySelector("[data-action=enable]")).not.toBeNull();
    expect(root.querySelector("[data-action=disable]")).toBeNull();
    expect(root.querySelector("[data-action=migrate-legacy]")).toBeNull();
  });

  it("renders diagnostic and upstream warning markup as text", () => {
    const root = document.createElement("div");
    const markup = '<img src=x onerror="alert(1)">';
    const data = { ...degraded, diagnostics: [{ code: markup, severity: "error", message: markup }], tailscale: { ...degraded.tailscale, Health: [markup] } };
    renderDashboard(root, parseRuntimeStatus(JSON.stringify(data)));
    expect(root.querySelector("img")).toBeNull();
    expect(root.textContent).toContain(markup);
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
