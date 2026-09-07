import { expect, test, type Page } from "@playwright/test";
import running from "../src/fixtures/running.json" with { type: "json" };
import degraded from "../src/fixtures/degraded.json" with { type: "json" };
import migration from "../src/fixtures/migration-required.json" with { type: "json" };

interface Fixture {
  status: unknown;
  commands: string[];
  failures: Record<string, string>;
  hanging: string[];
}
declare global { interface Window { __kst: Fixture } }

async function mockBridge(page: Page, status: unknown) {
  await page.addInitScript(({ status, running }) => {
    const fixture: Fixture = { status, commands: [], failures: {}, hanging: [] };
    window.__kst = fixture;
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: () => Promise.reject(new Error("clipboard denied")) } });
    Object.defineProperty(window, "ksu", { value: {
      exec(command: string, _options: string, callbackName: string) {
        const action = command.split(" ").at(-1)!;
        fixture.commands.push(action);
        if (fixture.hanging.includes(action)) return;
        let output = "done";
        if (action === "status-json") output = JSON.stringify(fixture.status);
        if (action === "logs") output = '<script>bad()</script>\nfixture log line';
        if (action === "diagnostics") output = `${JSON.stringify(fixture.status)}\nredacted log`;
        if (action === "migration-status") output = '{"state":"migration-required"}';
        if (action === "migrate-legacy") fixture.status = {
          ...running, lifecycle: "stopped", tailscale: null, prefs: null,
          components: { supervisor: "stopped", daemon: "stopped", dataPlane: "stopped", web: "stopped" },
          diagnostics: [{ code: "migration-awaiting-enable", severity: "info", message: "Migrated identity is preserved; explicit enable or start is required" }],
        };
        if (action === "apply-staged" || action === "enable") fixture.status = running;
        const error = fixture.failures[action];
        setTimeout(() => {
          const callback = (window as unknown as Record<string, (code: number, stdout: string, stderr: string) => void>)[callbackName];
          callback?.(error ? 1 : 0, error ? "" : output, error ?? "");
        }, 10);
      },
      toast() {},
    } });
  }, { status, running });
  await page.goto("/");
  await expect(page.locator("#app")).toHaveAttribute("aria-busy", "false");
}

async function checkLayout(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(await page.locator("button").evaluateAll((buttons) => buttons.every((button) => {
    const box = button.getBoundingClientRect();
    return box.width >= 44 && box.height >= 44 && button.scrollWidth <= button.clientWidth + 1;
  }))).toBe(true);
  await expect(page.locator("i[data-lucide]")).toHaveCount(0);
}

test("connected status and stable toolbar", async ({ page }, info) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await mockBridge(page, running);
  await expect(page.getByRole("heading", { name: "KernelSU-Tailscaled" })).toBeVisible();
  await expect(page.locator(".device-name")).toHaveText("pkx110");
  await checkLayout(page);
  await page.screenshot({ path: info.outputPath("running.png"), fullPage: true });
  await page.locator('[data-action="copy-ip"]').click();
  await expect(page.getByRole("alert")).toContainText("clipboard denied");
  await expect(page.locator('[data-action="copy-ip"]')).toBeEnabled();
  expect(errors).toEqual([]);
});

test("degraded status and confirmed staged activation", async ({ page }, info) => {
  await mockBridge(page, degraded);
  await expect(page.locator('[data-lifecycle="degraded"]')).toContainText("降级");
  await expect(page.locator('[data-state="unknown"]')).toContainText("未知");
  await expect(page.locator(".upstream-health")).toContainText("DNS server is unreachable");
  await checkLayout(page);
  await page.screenshot({ path: info.outputPath("degraded.png"), fullPage: true });
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.locator('[data-action="apply-staged"]').click();
  expect(await page.evaluate(() => window.__kst.commands)).not.toContain("apply-staged");
  page.once("dialog", (dialog) => dialog.accept());
  await page.locator('[data-action="apply-staged"]').click();
  await expect(page.locator('[data-lifecycle="running"]')).toBeVisible();
  expect(await page.evaluate(() => window.__kst.commands)).toContain("apply-staged");
});

test("explicit migration waits for a separate enable", async ({ page }, info) => {
  await mockBridge(page, migration);
  await checkLayout(page);
  await page.screenshot({ path: info.outputPath("migration.png"), fullPage: true });
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.locator('[data-action="migrate-legacy"]').click();
  expect(await page.evaluate(() => window.__kst.commands)).not.toContain("migrate-legacy");
  page.once("dialog", (dialog) => dialog.accept());
  await page.locator('[data-action="migrate-legacy"]').click();
  await expect(page.locator('[data-action="enable"]')).toBeEnabled();
  expect(await page.evaluate(() => window.__kst.commands)).not.toContain("enable");
  await expect(page.locator('[data-action="open-panel"]')).toBeDisabled();
  await page.locator('[data-action="enable"]').click();
  await expect(page.locator('[data-lifecycle="running"]')).toBeVisible();
});

test("command and log failures preserve the current view and recover buttons", async ({ page }, info) => {
  await mockBridge(page, running);
  await page.evaluate(() => { window.__kst.failures.restart = '<img src=x onerror="bad()"> restart failed'; });
  await page.locator('[data-action="restart"]').click();
  await expect(page.getByRole("alert")).toContainText("restart failed");
  await expect(page.locator("img")).toHaveCount(0);
  await expect(page.locator('[data-action="restart"]')).toBeEnabled();
  await page.locator('[data-action="logs"]').click();
  await expect(page.locator("pre")).toContainText("<script>bad()</script>");
  await page.evaluate(() => { window.__kst.failures.logs = "logs failed"; });
  await page.locator('[data-action="refresh-logs"]').click();
  await expect(page.getByRole("alert")).toContainText("logs failed");
  await expect(page.locator("pre")).toContainText("fixture log line");
  await expect(page.locator('[data-action="refresh-logs"]')).toBeEnabled();
  await checkLayout(page);
  await page.screenshot({ path: info.outputPath("logs-error.png"), fullPage: true });
  await page.locator('[data-action="back"]').click();
  await expect(page.locator('[data-lifecycle="running"]')).toBeVisible();
});

test("official panel navigation stays on the fixed loopback address", async ({ page }) => {
  await mockBridge(page, running);
  await page.route("http://127.0.0.1:8088/**", (route) => route.fulfill({ body: "Official panel fixture", contentType: "text/plain" }));
  await page.locator('[data-action="open-panel"]').click();
  await expect(page).toHaveURL("http://127.0.0.1:8088/");
});
