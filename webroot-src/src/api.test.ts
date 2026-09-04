import { describe, expect, it } from "vitest";
import { commandFor } from "./api";

describe("commandFor", () => {
  it.each([
    "status-json",
    "enable",
    "disable",
    "restart",
    "logs",
    "web-restart",
  ] as const)("maps the fixed %s action", (action) => {
    expect(commandFor(action)).toBe(
      `/data/adb/modules/magisk-tailscaled/tailscale/scripts/tailscale-service ${action}`,
    );
  });

  it("rejects a raw shell action", () => {
    expect(() => commandFor("status-json; id" as never)).toThrow("Unsupported action");
  });
});
