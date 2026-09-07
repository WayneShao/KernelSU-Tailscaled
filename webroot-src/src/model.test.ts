import { describe, expect, it } from "vitest";
import needsLogin from "./fixtures/needs-login.json";
import running from "./fixtures/running.json";
import stopped from "./fixtures/stopped.json";
import degraded from "./fixtures/degraded.json";
import migration from "./fixtures/migration-required.json";
import { parseRuntimeStatus } from "./model";

describe("parseRuntimeStatus", () => {
  it("uses a validated custom loopback panel endpoint", () => {
    expect(parseRuntimeStatus(JSON.stringify({ ...running, webListen: "127.0.0.1:9099" })).panelURL).toBe("http://127.0.0.1:9099/");
    expect(() => parseRuntimeStatus(JSON.stringify({ ...running, webListen: "example.com:8088" }))).toThrow();
    expect(() => parseRuntimeStatus(JSON.stringify({ ...running, webListen: "127.0.0.1:99999" }))).toThrow();
  });
  it("maps a connected native runtime", () => {
    const model = parseRuntimeStatus(JSON.stringify(running));

    expect(model).toMatchObject({
      enabled: true,
      mode: "native",
      hostname: "pkx110",
      backendState: "Running",
      ipv4: "100.64.10.20",
      acceptRoutes: false,
      acceptDNS: false,
      exitNode: null,
      schemaVersion: 2,
      lifecycle: "running",
      moduleVersion: "2.0.0-beta.1",
      tailscaleVersion: "1.102.3",
    });
  });

  it("treats NeedsLogin as a healthy daemon without an identity", () => {
    const model = parseRuntimeStatus(JSON.stringify(needsLogin));

    expect(model.backendState).toBe("NeedsLogin");
    expect(model.hostname).toBeNull();
    expect(model.ipv4).toBeNull();
    expect(model.components.daemon).toBe("running");
  });

  it("falls back to the reported hostname when the backend DNS name is absent", () => {
    const data = structuredClone(running);
    data.tailscale.Self.HostName = "phone-fallback";
    data.tailscale.Self.DNSName = "";

    expect(parseRuntimeStatus(JSON.stringify(data)).hostname).toBe("phone-fallback");
  });

  it("maps a disabled runtime without inventing Tailscale fields", () => {
    const model = parseRuntimeStatus(JSON.stringify(stopped));

    expect(model.enabled).toBe(false);
    expect(model.backendState).toBe("Stopped");
    expect(model.acceptRoutes).toBeNull();
    expect(model.acceptDNS).toBeNull();
  });

  it("rejects trailing output after the JSON document", () => {
    expect(() => parseRuntimeStatus(`${JSON.stringify(running)}\nnoise`)).toThrow(
      "Invalid runtime status",
    );
  });

  it("rejects invalid component states", () => {
    const invalid = structuredClone(running);
    invalid.components.web = "unhealthy";

    expect(() => parseRuntimeStatus(JSON.stringify(invalid))).toThrow(
      "Invalid runtime status",
    );
  });
  it("preserves lifecycle, unknown health, diagnostics and effective preferences", () => {
    expect(parseRuntimeStatus(JSON.stringify(degraded))).toMatchObject({
      lifecycle: "degraded", backendState: "Running", health: ["DNS server is unreachable"],
      components: { dataPlane: "unknown", web: "stopped" }, acceptRoutes: true,
      acceptDNS: true, exitNode: "exit-node-id", runtime: degraded.runtime, diagnostics: degraded.diagnostics,
    });
  });

  it("keeps migration intent distinct from running and permits absent runtime metadata", () => {
    expect(parseRuntimeStatus(JSON.stringify(migration))).toMatchObject({
      enabled: true, lifecycle: "migration-required", backendState: "Unknown",
      runtime: { activeVersion: null }, hostname: null,
    });
  });

  it("retains the admin name even when IPs are null", () => {
    const data = { ...running, tailscale: { ...running.tailscale, Self: { ...running.tailscale.Self, TailscaleIPs: null } } };
    expect(parseRuntimeStatus(JSON.stringify(data)).hostname).toBe("pkx110");
  });

  it.each([
    { schemaVersion: 1 }, { lifecycle: "fictional" }, { runtime: {} },
    { diagnostics: [{ code: "x", severity: "fatal", message: "bad" }] },
    { tailscale: { BackendState: "Running", Health: [42] } },
  ])("rejects malformed schema fields: %j", (change) => {
    expect(() => parseRuntimeStatus(JSON.stringify({ ...running, ...change }))).toThrow("Invalid runtime status");
  });
});
