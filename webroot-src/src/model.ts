export type ComponentState = "running" | "stopped" | "unknown";
const LIFECYCLES = ["disabled", "stopped", "starting", "running", "degraded", "failed", "migration-required"] as const;
export type Lifecycle = typeof LIFECYCLES[number];

export interface Diagnostic {
  code: string;
  severity: "info" | "warning" | "error";
  message: string;
}

export interface RuntimeComponents {
  supervisor: ComponentState;
  daemon: ComponentState;
  dataPlane: ComponentState;
  web: ComponentState;
}

export interface RuntimeStatus {
  schemaVersion: 2;
  enabled: boolean;
  lifecycle: Lifecycle;
  mode: "native" | "userspace";
  panelURL: string;
  hostname: string | null;
  backendState: string;
  ipv4: string | null;
  acceptRoutes: boolean | null;
  acceptDNS: boolean | null;
  exitNode: string | null;
  moduleVersion: string;
  tailscaleVersion: string;
  components: RuntimeComponents;
  runtime: { activeVersion: string | null; stagedVersion: string | null; previousVersion: string | null };
  diagnostics: Diagnostic[];
  health: string[];
}

type JsonObject = Record<string, unknown>;

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireString(object: JsonObject, key: string): string {
  const value = object[key];
  if (typeof value !== "string") {
    throw new Error("Invalid runtime status");
  }
  return value;
}

function requireComponent(value: unknown): ComponentState {
  if (value !== "running" && value !== "stopped" && value !== "unknown") {
    throw new Error("Invalid runtime status");
  }
  return value;
}

function nullableString(value: unknown): string | null {
  if (value !== null && typeof value !== "string") throw new Error("Invalid runtime status");
  return value;
}

function stringList(value: unknown): string[] {
  if (value === null || value === undefined) return [];
  if (!Array.isArray(value) || !value.every((item) => typeof item === "string")) throw new Error("Invalid runtime status");
  return value;
}

export function parseRuntimeStatus(input: string): RuntimeStatus {
  try {
    const raw: unknown = JSON.parse(input);
    if (!isObject(raw) || raw.schemaVersion !== 2 || typeof raw.enabled !== "boolean" || !isObject(raw.components) || !isObject(raw.runtime)) {
      throw new Error("Invalid runtime status");
    }

    if (!LIFECYCLES.includes(raw.lifecycle as Lifecycle) || !Array.isArray(raw.diagnostics)) throw new Error("Invalid runtime status");
    const lifecycle = raw.lifecycle as Lifecycle;
    const diagnostics: Diagnostic[] = raw.diagnostics.map((item: unknown) => {
      if (!isObject(item) || !["info", "warning", "error"].includes(String(item.severity))) throw new Error("Invalid runtime status");
      return { code: requireString(item, "code"), severity: item.severity as Diagnostic["severity"], message: requireString(item, "message") };
    });
    const runtime = {
      activeVersion: nullableString(raw.runtime.activeVersion),
      stagedVersion: nullableString(raw.runtime.stagedVersion),
      previousVersion: nullableString(raw.runtime.previousVersion),
    };

    const mode = raw.mode;
    if (mode !== "native" && mode !== "userspace") {
      throw new Error("Invalid runtime status");
    }

    const components: RuntimeComponents = {
      supervisor: requireComponent(raw.components.supervisor),
      daemon: requireComponent(raw.components.daemon),
      dataPlane: requireComponent(raw.components.dataPlane),
      web: requireComponent(raw.components.web),
    };

    let backendState = raw.enabled ? "Unknown" : "Stopped";
    let hostname: string | null = null;
    let ipv4: string | null = null;
    let health: string[] = [];
    if (raw.tailscale !== null) {
      if (!isObject(raw.tailscale)) {
        throw new Error("Invalid runtime status");
      }
      backendState = requireString(raw.tailscale, "BackendState");
      health = stringList(raw.tailscale.Health);
      if (raw.tailscale.Self !== null && raw.tailscale.Self !== undefined) {
        if (!isObject(raw.tailscale.Self)) {
          throw new Error("Invalid runtime status");
        }
        const hostName = requireString(raw.tailscale.Self, "HostName");
        const dnsNameValue = raw.tailscale.Self.DNSName;
        if (dnsNameValue !== undefined && typeof dnsNameValue !== "string") {
          throw new Error("Invalid runtime status");
        }
        const ips = stringList(raw.tailscale.Self.TailscaleIPs);
        const dnsLabel = dnsNameValue?.replace(/\.$/, "").split(".")[0] ?? "";
        hostname = dnsLabel || hostName || null;
        ipv4 = ips.find((value) => /^\d{1,3}(?:\.\d{1,3}){3}$/.test(value)) ?? null;
      }
    }

    let acceptRoutes: boolean | null = null;
    let acceptDNS: boolean | null = null;
    let exitNode: string | null = null;
    if (raw.prefs !== null) {
      if (!isObject(raw.prefs) || typeof raw.prefs.RouteAll !== "boolean" || typeof raw.prefs.CorpDNS !== "boolean") {
        throw new Error("Invalid runtime status");
      }
      acceptRoutes = raw.prefs.RouteAll;
      acceptDNS = raw.prefs.CorpDNS;
      const exitNodeID = raw.prefs.ExitNodeID;
      if (typeof exitNodeID !== "string") {
        throw new Error("Invalid runtime status");
      }
      exitNode = exitNodeID || null;
    }

    const webListen = raw.webListen ?? "127.0.0.1:8088";
    if (typeof webListen !== "string" || !/^127\.0\.0\.1:[1-9][0-9]{0,4}$/.test(webListen) || Number(webListen.split(":")[1]) > 65535) {
      throw new Error("Invalid runtime status");
    }
    return {
      schemaVersion: 2,
      enabled: raw.enabled,
      lifecycle,
      mode,
      panelURL: `http://${webListen}/`,
      hostname,
      backendState,
      ipv4,
      acceptRoutes,
      acceptDNS,
      exitNode,
      moduleVersion: requireString(raw, "moduleVersion"),
      tailscaleVersion: requireString(raw, "tailscaleVersion"),
      components,
      runtime,
      diagnostics,
      health,
    };
  } catch {
    throw new Error("Invalid runtime status");
  }
}
