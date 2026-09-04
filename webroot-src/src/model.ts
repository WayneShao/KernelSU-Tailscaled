export type ComponentState = "running" | "stopped";

export interface RuntimeComponents {
  supervisor: ComponentState;
  daemon: ComponentState;
  dataPlane: ComponentState;
  web: ComponentState;
}

export interface RuntimeStatus {
  enabled: boolean;
  mode: "native" | "userspace";
  hostname: string | null;
  backendState: string;
  ipv4: string | null;
  acceptRoutes: boolean | null;
  acceptDNS: boolean | null;
  exitNode: string | null;
  moduleVersion: string;
  tailscaleVersion: string;
  components: RuntimeComponents;
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
  if (value !== "running" && value !== "stopped") {
    throw new Error("Invalid runtime status");
  }
  return value;
}

export function parseRuntimeStatus(input: string): RuntimeStatus {
  try {
    const raw: unknown = JSON.parse(input);
    if (!isObject(raw) || typeof raw.enabled !== "boolean" || !isObject(raw.components)) {
      throw new Error("Invalid runtime status");
    }

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
    if (raw.tailscale !== null) {
      if (!isObject(raw.tailscale)) {
        throw new Error("Invalid runtime status");
      }
      backendState = requireString(raw.tailscale, "BackendState");
      if (raw.tailscale.Self !== null) {
        if (!isObject(raw.tailscale.Self)) {
          throw new Error("Invalid runtime status");
        }
        const hostName = requireString(raw.tailscale.Self, "HostName");
        const dnsNameValue = raw.tailscale.Self.DNSName;
        if (dnsNameValue !== undefined && typeof dnsNameValue !== "string") {
          throw new Error("Invalid runtime status");
        }
        const ips = raw.tailscale.Self.TailscaleIPs;
        if (ips !== null && (!Array.isArray(ips) || !ips.every((value) => typeof value === "string"))) {
          throw new Error("Invalid runtime status");
        }
        if (Array.isArray(ips)) {
          const dnsLabel = dnsNameValue?.replace(/\.$/, "").split(".")[0] ?? "";
          hostname = dnsLabel || hostName || null;
          ipv4 = ips.find((value) => /^\d{1,3}(?:\.\d{1,3}){3}$/.test(value)) ?? null;
        }
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

    return {
      enabled: raw.enabled,
      mode,
      hostname,
      backendState,
      ipv4,
      acceptRoutes,
      acceptDNS,
      exitNode,
      moduleVersion: requireString(raw, "moduleVersion"),
      tailscaleVersion: requireString(raw, "tailscaleVersion"),
      components,
    };
  } catch {
    throw new Error("Invalid runtime status");
  }
}
