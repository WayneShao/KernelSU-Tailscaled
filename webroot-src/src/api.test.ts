import { afterEach, describe, expect, it, vi } from "vitest";
import { exec } from "kernelsu";
import { commandFor, runAction } from "./api";

vi.mock("kernelsu", () => ({ exec: vi.fn() }));
afterEach(() => vi.useRealTimers());

describe("commandFor", () => {
  it.each([
    "status-json",
    "enable",
    "disable",
    "restart",
    "logs",
    "web-restart",
    "diagnostics",
    "migration-status",
    "migrate-legacy",
    "apply-staged",
  ] as const)("maps the fixed %s action", (action) => {
    expect(commandFor(action)).toMatch(new RegExp(`^/data/adb/ksu/bin/busybox timeout -s KILL \\d+ sh /data/adb/modules/kernelsu-tailscaled/control.sh ${action}$`));
  });

  it("rejects a raw shell action", () => {
    expect(() => commandFor("status-json; id" as never)).toThrow("Unsupported action");
  });
  it("reserves time for a contended runtime lock and startup", () => {
    expect(commandFor("restart")).toContain("KILL 85 ");
    expect(commandFor("status-json")).toContain("KILL 35 ");
  });

  it("has a real deadline when the KernelSU callback never arrives", async () => {
    vi.useFakeTimers();
    vi.mocked(exec).mockReturnValue(new Promise(() => {}));
    const pending = expect(runAction("restart")).rejects.toThrow(/90/);
    await vi.advanceTimersByTimeAsync(90_000);
    await pending;
  });

  it("bounds status by the remaining panel-wait budget", async () => {
    vi.useFakeTimers();
    vi.mocked(exec).mockReturnValue(new Promise(() => {}));
    const pending = expect(runAction("status-json", 4_000)).rejects.toThrow(/超时/);
    expect(vi.mocked(exec).mock.lastCall?.[0]).toContain("KILL 3 ");
    await vi.advanceTimersByTimeAsync(4_000);
    await pending;
  });

  it("normalizes command output and clears its deadline", async () => {
    vi.useFakeTimers();
    vi.mocked(exec).mockResolvedValue({ stdout: "{}", stderr: "", errno: 0 });
    expect(await runAction("status-json")).toEqual({ stdout: "{}", stderr: "", exitCode: 0 });
    expect(vi.getTimerCount()).toBe(0);
  });
});
