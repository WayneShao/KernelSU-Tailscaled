import { afterEach, beforeEach, expect, it, vi } from "vitest";

// Dynamic imports deliberately exercise locale initialization across module reloads.

beforeEach(() => { vi.resetModules(); localStorage.clear(); });
afterEach(() => { vi.restoreAllMocks(); localStorage.clear(); });

it("retains a selected locale after reloading the module", async () => {
  const locale = await import("./i18n");
  locale.setLanguage("zh-CN");
  vi.resetModules();
  const reloaded = await import("./i18n");
  expect(reloaded.getLanguage()).toBe("zh-CN");
  expect(document.documentElement.lang).toBe("zh-CN");
  reloaded.setLanguage("en");
  vi.resetModules();
  expect((await import("./i18n")).getLanguage()).toBe("en");
});

it("still switches language when WebView storage is unavailable", async () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("denied"); });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("denied"); });
  const locale = await import("./i18n");
  locale.setLanguage("zh-CN");
  expect(locale.getLanguage()).toBe("zh-CN");
  expect(locale.t("a", "b")).toBe("b");
  expect(document.documentElement.lang).toBe("zh-CN");
});
