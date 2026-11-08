import { afterEach, describe, expect, it, vi } from "vitest";
import { exec } from "kernelsu";
import { commandFor, runAction } from "./api";

vi.mock("kernelsu", () => ({ exec: vi.fn() }));
afterEach(() => vi.useRealTimers());

describe("commandFor", () => {
  it("rejects a raw shell action", () => {
    expect(() => commandFor("status-json; id" as never)).toThrow("Unsupported action");
  });

  it.each(["", "/data/adb", "/sdcard", "/sdcard/", "/sdcard/Download/", "/sdcard//Download", "/sdcard/../data", "/storage", "/storage/emulated/0", "/storage/emulated/0/./Download", "/storage/emulated/not-a-user/Download", "/storage/self/primary", "/storage/ABCD-1234", "/storage/self/other/Download", "/sdcard/Download\nrestart", "/sdcard/Download\u0000", "/sdcard/Download\u007f", "/sdcard/Download\u0085"])("rejects unsafe Taildrop input %j before the bridge", (directory) => {
    expect(() => commandFor("taildrop-save-dir", undefined, directory)).toThrow();
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
    const pending = expect(runAction("status-json", 4_000)).rejects.toThrow();
    await vi.advanceTimersByTimeAsync(4_000);
    await pending;
  });

});
