import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { exec, toast } from "kernelsu";
import running from "./fixtures/running.json";
import degraded from "./fixtures/degraded.json";
import migration from "./fixtures/migration-required.json";
import stopped from "./fixtures/stopped.json";

vi.mock("kernelsu", () => ({ exec: vi.fn(), toast: vi.fn() }));
const result = (stdout: string, errno = 0) => ({ stdout, stderr: "", errno });
const button = (action: string) => document.querySelector<HTMLButtonElement>(`[data-action="${action}"]`)!;
const settled = async () => vi.waitFor(() => expect(document.querySelector("#app")?.getAttribute("aria-busy")).toBe("false"));

async function boot(data: unknown = running) {
  vi.mocked(exec).mockResolvedValue(result(JSON.stringify(data)));
  await import("./main");
  await settled();
}

beforeEach(() => {
  vi.resetModules();
  vi.resetAllMocks();
  localStorage.clear();
  document.body.innerHTML = '<main id="app"></main>';
});
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

describe("dashboard actions", () => {
  it("switches language without dropping a server draft or re-executing commands", async () => {
    await boot();
    document.querySelector<HTMLInputElement>("#login-server")!.value = "https://draft.example.com";
    const calls = vi.mocked(exec).mock.calls.length;
    const select = document.querySelector<HTMLSelectElement>("[data-language]")!;
    select.value = "zh-CN";
    select.dispatchEvent(new Event("change", { bubbles: true }));
    expect(document.documentElement.lang).toBe("zh-CN");
    expect(document.querySelector<HTMLInputElement>("#login-server")!.value).toBe("https://draft.example.com");
    expect(vi.mocked(exec).mock.calls).toHaveLength(calls);
    expect(button("restart").disabled).toBe(false);
  });

  it("never renders an executable auth URL returned by the backend", async () => {
    await boot();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(exec).mockResolvedValueOnce(result(JSON.stringify({ controlURL: "https://example.com", authURL: "javascript:alert(1)" })));
    document.querySelector("form[data-server]")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await settled();
    expect(document.querySelector(".sign-in-link")).toBeNull();
    expect(document.querySelector('[role="alert"]')).not.toBeNull();
    expect(document.querySelector<HTMLButtonElement>("form button")!.disabled).toBe(false);
  });

  it('checks and prepares engines through fixed actions without applying automatically', async () => {
    await boot();
    vi.mocked(exec).mockResolvedValueOnce(result('{"current":"1.104.2","latest":"","staged":""}'));
    button('engine-page').click();
    await settled();
    vi.mocked(exec).mockResolvedValueOnce(result('{"current":"1.104.2","latest":"1.106.0","staged":""}'));
    button('engine-check').click();
    await settled();
    vi.mocked(exec).mockResolvedValueOnce(result('{"current":"1.104.2","latest":"1.106.0","staged":"1.106.0"}'));
    button('engine-prepare').click();
    await settled();
    expect(button('engine-apply')).not.toBeNull();
    expect(vi.mocked(exec).mock.calls.some(([command]) => command.endsWith(' engine-apply'))).toBe(false);
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    button('engine-apply').click();
    await settled();
    expect(vi.mocked(exec).mock.calls.some(([command]) => command.endsWith(' engine-apply'))).toBe(false);
  });
  it("restores valid buttons after a failing command without losing the dashboard", async () => {
    await boot();
    vi.mocked(exec).mockResolvedValueOnce(result("restart failed", 1));
    button("restart").click();
    await settled();
    expect(document.querySelector('[role="alert"]')?.textContent).toContain("restart failed");
    expect(button("restart")?.disabled).toBe(false);
    expect(button("refresh")?.disabled).toBe(false);
    expect(button("copy-ip")?.disabled).toBe(false);
  });

  it("keeps intrinsic disabled controls disabled after failure", async () => {
    await boot(stopped);
    vi.mocked(exec).mockResolvedValueOnce(result("enable failed", 1));
    button("enable").click();
    await settled();
    expect(button("enable")?.disabled).toBe(false);
    expect(button("restart")?.disabled).toBe(true);
    expect(button("copy-ip")?.disabled).toBe(true);
  });

  it("catches clipboard rejection and retains working controls", async () => {
    await boot();
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: vi.fn().mockRejectedValue(new Error("clipboard denied")) } });
    button("copy-ip").click();
    await settled();
    await vi.waitFor(() => expect(document.querySelector('[role="alert"]')?.textContent).toContain("clipboard denied"));
    expect(button("copy-ip")?.disabled).toBe(false);
    expect(toast).not.toHaveBeenCalled();
  });

  it.each([
    ["migrate-legacy", migration], ["apply-staged", degraded],
  ] as const)("cancels confirmation for %s without executing", async (action, data) => {
    await boot(data);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const previousCalls = vi.mocked(exec).mock.calls.length;
    button(action).click();
    await settled();
    expect(confirm).toHaveBeenCalledOnce();
    expect(vi.mocked(exec).mock.calls).toHaveLength(previousCalls);
    expect(button(action)?.disabled).toBe(false);
  });

  it("migrates only after confirmation and never starts the imported identity", async () => {
    await boot(migration);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const imported = { ...migration, lifecycle: "stopped", diagnostics: [{ code: "migration-awaiting-enable", severity: "info", message: "Explicit enable required" }] };
    vi.mocked(exec).mockResolvedValueOnce(result("copied")).mockResolvedValueOnce(result(JSON.stringify(imported)));
    button("migrate-legacy").click();
    await settled();
    expect(vi.mocked(exec).mock.calls.some(([command]) => command.endsWith(" migrate-legacy"))).toBe(true);
    expect(vi.mocked(exec).mock.calls.some(([command]) => / (enable|restart|start)$/.test(command))).toBe(false);
    expect(button("enable")?.disabled).toBe(false);
  });

  it("applies a staged runtime only after confirmation and refreshes actual state", async () => {
    await boot(degraded);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(exec).mockResolvedValueOnce(result("applied")).mockResolvedValueOnce(result(JSON.stringify(running)));
    button("apply-staged").click();
    await settled();
    expect(vi.mocked(exec).mock.calls.some(([command]) => command.endsWith(" apply-staged"))).toBe(true);
    expect(button("apply-staged")).toBeNull();
    expect(button("restart")?.disabled).toBe(false);
  });

  it("shows logs as text and retains them when log refresh fails", async () => {
    await boot();
    vi.mocked(exec).mockResolvedValueOnce(result("<script>bad()</script>\nlog line"));
    button("logs").click();
    await settled();
    expect(document.querySelector("pre")?.textContent).toContain("<script>bad()</script>");
    expect(document.querySelector("script")).toBeNull();
    vi.mocked(exec).mockResolvedValueOnce(result("logs failed", 1));
    button("refresh-logs").click();
    await settled();
    expect(document.querySelector("pre")?.textContent).toContain("log line");
    expect(document.querySelector('[role="alert"]')?.textContent).toContain("logs failed");
    expect(button("refresh-logs")?.disabled).toBe(false);
    expect(button("back")?.disabled).toBe(false);
  });

  it("renders diagnostic output as plain text", async () => {
    await boot();
    vi.mocked(exec).mockResolvedValueOnce(result("{\"schemaVersion\":2}\nredacted diagnostic log"));
    button("diagnostics").click();
    await settled();
    expect(document.querySelector("pre")?.textContent).toContain("redacted diagnostic log");
  });

  it("shows malformed status as an error with a usable retry", async () => {
    vi.mocked(exec).mockResolvedValue(result("not json"));
    await import("./main");
    await settled();
    expect(document.body.textContent).toContain("Invalid runtime status");
    expect(button("refresh").disabled).toBe(false);
  });

  it("recovers buttons after a mutation callback exceeds its deadline", async () => {
    await boot();
    vi.useFakeTimers();
    vi.mocked(exec).mockReturnValueOnce(new Promise(() => {}));
    button("restart").click();
    expect(button("refresh").disabled).toBe(true);
    await vi.advanceTimersByTimeAsync(90_000);
    expect(button("restart")?.disabled).toBe(false);
  });

  it("bounds the complete wait for the panel even when status never returns", async () => {
    await boot(degraded);
    vi.useFakeTimers();
    vi.mocked(exec).mockResolvedValueOnce(result("web started")).mockReturnValueOnce(new Promise(() => {}));
    button("open-panel").click();
    await vi.advanceTimersByTimeAsync(20_000);
    expect(button("open-panel")?.disabled).toBe(false);
    expect(vi.mocked(exec).mock.calls.filter(([command]) => command.endsWith(" status-json"))).toHaveLength(2);
  });

  it("stops polling after the panel budget expires without restarting the VPN", async () => {
    await boot(degraded);
    vi.useFakeTimers();
    vi.mocked(exec).mockResolvedValueOnce(result("web started")).mockResolvedValue(result(JSON.stringify(degraded)));
    button("open-panel").click();
    await vi.advanceTimersByTimeAsync(20_000);
    const calls = vi.mocked(exec).mock.calls.length;
    await vi.advanceTimersByTimeAsync(90_000);
    expect(vi.mocked(exec).mock.calls).toHaveLength(calls);
    expect(vi.mocked(exec).mock.calls.some(([command]) => command.endsWith(" restart"))).toBe(false);
    expect(button("open-panel")?.disabled).toBe(false);
  });
});
