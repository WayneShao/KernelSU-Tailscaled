import {
  ArrowLeft,
  Circle,
  Copy,
  createIcons,
  ExternalLink,
  Import,
  ListChecks,
  PackageCheck,
  Power,
  PowerOff,
  RefreshCw,
  RotateCw,
  ScrollText,
  Stethoscope,
} from "lucide";
import { toast } from "kernelsu";
import { runAction, type ModuleAction } from "./api";
import { parseRuntimeStatus, type RuntimeStatus } from "./model";
import { renderDashboard, renderLogs, renderMessage, renderEngineUpdate } from "./render";
import { parseEngineStatus } from './engine';
import { setLanguage, t } from "./i18n";
import { controlURL, parseLoginResult, renderLoginResult } from "./server";
import { taildropDirectory } from "./taildrop";
import "./styles.css";

const applicationRoot = document.querySelector<HTMLElement>("#app");
if (!applicationRoot) throw new Error("Missing application root");
const root: HTMLElement = applicationRoot;

let currentStatus: RuntimeStatus | null = null;
let busy = false;
const idleDisabled = new WeakMap<HTMLButtonElement | HTMLInputElement | HTMLSelectElement, boolean>();
let redraw: () => void = () => renderMessage(root, t("Reading status", "正在读取状态"), t("Please wait", "请稍候"));

function drawIcons(): void {
  createIcons({
    icons: { ArrowLeft, Circle, Copy, ExternalLink, Import, ListChecks, PackageCheck, Power, PowerOff, RefreshCw, RotateCw, ScrollText, Stethoscope },
    attrs: { "stroke-width": 2, width: 18, height: 18 },
  });
}

function setBusy(value: boolean): void {
  busy = value;
  root.querySelectorAll<HTMLButtonElement | HTMLInputElement | HTMLSelectElement>("button, input, select").forEach((control) => {
    if (value) {
      if (!idleDisabled.has(control)) idleDisabled.set(control, control.disabled);
      control.disabled = true;
    } else if (idleDisabled.has(control)) {
      control.disabled = idleDisabled.get(control)!;
      idleDisabled.delete(control);
    }
  });
  root.setAttribute("aria-busy", String(value));
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function announce(message: string, isError = false): void {
  root.querySelector(".notice")?.remove();
  const notice = document.createElement("p");
  notice.className = "notice";
  notice.setAttribute("role", isError ? "alert" : "status");
  notice.textContent = message;
  root.querySelector("header")?.after(notice);
}

async function execute(action: ModuleAction, remainingMs?: number, input?: string): Promise<string> {
  const result = await runAction(action, remainingMs, input);
  if (result.exitCode !== 0) {
    throw new Error(result.stderr.trim() || result.stdout.trim() || t(`Command failed (${result.exitCode})`, `命令失败 (${result.exitCode})`));
  }
  return result.stdout;
}

async function refreshStatus(): Promise<void> {
  currentStatus = parseRuntimeStatus(await execute("status-json"));
  const status = currentStatus;
  redraw = () => renderDashboard(root, status);
  redraw();
  drawIcons();
}

async function showLogs(kind: "logs" | "diagnostics"): Promise<void> {
  const logs = await execute(kind);
  redraw = () => renderLogs(root, logs, kind);
  redraw();
  drawIcons();
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function waitForWeb(): Promise<void> {
  const deadline = Date.now() + 20_000;
  while (Date.now() < deadline - 2_000) {
    const status = parseRuntimeStatus(await execute("status-json", deadline - Date.now()));
    currentStatus = status;
    if (status.components.web === "running") return;
    await delay(Math.min(500, Math.max(0, deadline - Date.now())));
  }
  throw new Error(t("Local panel startup timed out. Refresh status to check the result.", "本地面板启动超时，请刷新状态确认结果"));
}

async function openPanel(): Promise<void> {
  if (currentStatus?.components.web !== "running") {
    await execute("web-restart");
    await waitForWeb();
  }
  if (!currentStatus) throw new Error(t("Status unavailable", "状态不可用"));
  window.location.href = currentStatus.panelURL;
}

async function handleAction(action: string): Promise<void> {
  if (busy) return;
  if (action === 'engine-apply' && !window.confirm(t("Apply the verified Tailscale engine? The service will restart briefly. Your login and settings will be retained.", "应用已校验的 Tailscale 引擎？服务会短暂重启，登录与配置保留。"))) return;
  if (action === "migrate-legacy" && !window.confirm(t("Migrate the legacy module identity?\nThe old module must be disabled or removed, both runtimes stopped, and no new identity present. Old files will be kept. Enable separately after migration.", "迁移旧模块身份？\n旧模块须已禁用或移除，且旧、新运行时均已停止；新身份必须不存在。旧文件将保留，迁移后等待单独启用。"))) return;
  if (action === "apply-staged" && !window.confirm(t("Apply the staged runtime?\nThe current runtime will stop and switch to the verified staged version. This updates the runtime, not the current manager WebUI, and does not reboot the device.", "应用暂存运行时？\n当前运行时将停止并切换至已验证的暂存版本。此操作更新运行时，不更新当前管理器中的 WebUI，也不重启设备。"))) return;
  setBusy(true);
  announce(t("Working…", "处理中"));
  try {
    switch (action) {
      case 'engine-page':
      case 'engine-status':
      case 'engine-check':
      case 'engine-prepare':
      case 'engine-apply': {
        const command = action === 'engine-page' ? 'engine-status' : action;
        announce(action === 'engine-prepare' ? t("Downloading and verifying; the current service will keep running…", "正在下载并校验，当前服务继续运行…") : t("Working…", "处理中"));
        const engine = parseEngineStatus(await execute(command));
        redraw = () => renderEngineUpdate(root, engine);
        redraw();
        drawIcons();
        break;
      }
      case "refresh":
      case "back":
        await refreshStatus();
        break;
      case "logs":
      case "refresh-logs":
        await showLogs("logs");
        break;
      case "diagnostics":
      case "refresh-diagnostics":
        await showLogs("diagnostics");
        break;
      case "migration-status": {
        const labels: Record<string, string> = {
          "migration-incomplete": t("Migration incomplete", "迁移未完成"), "awaiting-enable": t("Migrated; waiting for enable", "已迁移，待启用"),
          "destination-exists": t("New module identity already exists", "新模块身份已存在"), "migration-required": t("Migration required", "待迁移"),
          "no-legacy-identity": t("No legacy identity found", "未发现旧身份"),
        };
        const data: unknown = JSON.parse(await execute("migration-status"));
        if (!data || typeof data !== "object" || !("state" in data) || typeof data.state !== "string" || !Object.hasOwn(labels, data.state)) throw new Error("Invalid migration status");
        announce(labels[data.state]!);
        break;
      }
      case "copy-ip":
        if (currentStatus?.ipv4) {
          await navigator.clipboard.writeText(currentStatus.ipv4);
          announce(t("Tailscale IP copied", "Tailscale IP 已复制"));
          toast(t("Tailscale IP copied", "Tailscale IP 已复制"));
        }
        break;
      case "open-panel":
        await openPanel();
        break;
      case "enable":
      case "disable":
      case "restart":
      case "migrate-legacy":
      case "apply-staged":
        await execute(action);
        await refreshStatus();
        break;
    }
  } catch (error) {
    if (!currentStatus) {
      redraw = () => renderMessage(root, t("Status unavailable", "状态不可用"), errorMessage(error));
      redraw();
      drawIcons();
    }
    announce(errorMessage(error), true);
  } finally {
    setBusy(false);
  }
}

root.addEventListener("change", (event) => {
  const select = event.target as HTMLSelectElement;
  if (!select.matches("select[data-language]") || busy) return;
  if (select.value !== "en" && select.value !== "zh-CN") return;
  const drafts = ["login-server", "taildrop-directory"].map((id) => ({ id, value: root.querySelector<HTMLInputElement>(`#${id}`)?.value }));
  setLanguage(select.value);
  redraw();
  for (const draft of drafts) {
    const input = root.querySelector<HTMLInputElement>(`#${draft.id}`);
    if (input && draft.value !== undefined) input.value = draft.value;
  }
  drawIcons();
});

root.addEventListener("submit", async (event) => {
  const form = event.target as HTMLFormElement;
  if (!form.matches("form[data-server], form[data-taildrop]")) return;
  event.preventDefault();
  if (busy) return;
  try {
    const isTaildrop = form.hasAttribute("data-taildrop");
    const input = form.querySelector<HTMLInputElement>("input")!.value;
    const value = isTaildrop ? taildropDirectory(input) : controlURL(input);
    if (!isTaildrop && !window.confirm(t(`Connect to ${value}? This can disconnect your current network. Complete registration on the selected server afterward.`, `连接到 ${value}？这可能断开当前网络。随后请在所选服务器完成注册。`))) return;
    setBusy(true);
    announce(isTaildrop ? t("Saving Taildrop folder…", "正在保存 Taildrop 文件夹…") : t("Connecting to control server…", "正在连接控制服务器…"));
    const response = await execute(isTaildrop ? "taildrop-save-dir" : "login-server", undefined, value);
    const result = isTaildrop ? null : parseLoginResult(response);
    await refreshStatus();
    if (result) {
      const dashboard = redraw;
      redraw = () => { dashboard(); renderLoginResult(root, result); };
      redraw();
      drawIcons();
    } else {
      announce(t("Taildrop folder saved.", "Taildrop 文件夹已保存。"));
    }
  } catch (error) {
    announce(errorMessage(error), true);
  } finally {
    setBusy(false);
  }
});

root.addEventListener("click", (event) => {
  const button = (event.target as Element).closest<HTMLButtonElement>("button[data-action]");
  if (button?.dataset.action) void handleAction(button.dataset.action);
});

redraw();
drawIcons();
void handleAction("refresh");
