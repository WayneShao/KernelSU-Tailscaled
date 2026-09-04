import { describe, expect, it } from "vitest";
import needsLogin from "./fixtures/needs-login.json";
import running from "./fixtures/running.json";
import stopped from "./fixtures/stopped.json";
import { parseRuntimeStatus } from "./model";

describe("parseRuntimeStatus", () => {
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
      moduleVersion: "1.102.3.1",
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
    invalid.components.web = "unknown";

    expect(() => parseRuntimeStatus(JSON.stringify(invalid))).toThrow(
      "Invalid runtime status",
    );
  });
});
