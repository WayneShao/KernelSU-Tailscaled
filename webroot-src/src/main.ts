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
import { renderDashboard, renderLogs, renderMessage } from "./render";
import "./styles.css";

const applicationRoot = document.querySelector<HTMLElement>("#app");
if (!applicationRoot) throw new Error("Missing application root");
const root: HTMLElement = applicationRoot;

let currentStatus: RuntimeStatus | null = null;
let busy = false;
const idleDisabled = new WeakMap<HTMLButtonElement, boolean>();

function drawIcons(): void {
  createIcons({
    icons: { ArrowLeft, Circle, Copy, ExternalLink, Import, ListChecks, PackageCheck, Power, PowerOff, RefreshCw, RotateCw, ScrollText, Stethoscope },
    attrs: { "stroke-width": 2, width: 18, height: 18 },
  });
}

function setBusy(value: boolean): void {
  busy = value;
  root.querySelectorAll<HTMLButtonElement>("button").forEach((button) => {
    if (value) {
      if (!idleDisabled.has(button)) idleDisabled.set(button, button.disabled);
      button.disabled = true;
    } else if (idleDisabled.has(button)) {
      button.disabled = idleDisabled.get(button)!;
      idleDisabled.delete(button);
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

async function execute(action: ModuleAction, remainingMs?: number): Promise<string> {
  const result = await runAction(action, remainingMs);
  if (result.exitCode !== 0) {
    throw new Error(result.stderr.trim() || result.stdout.trim() || `命令失败 (${result.exitCode})`);
  }
  return result.stdout;
}

async function refreshStatus(): Promise<void> {
  currentStatus = parseRuntimeStatus(await execute("status-json"));
  renderDashboard(root, currentStatus);
  drawIcons();
}

async function showLogs(kind: "logs" | "diagnostics"): Promise<void> {
  renderLogs(root, await execute(kind), kind);
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
  throw new Error("本地面板启动超时，请刷新状态确认结果");
}

async function openPanel(): Promise<void> {
  if (currentStatus?.components.web !== "running") {
    await execute("web-restart");
    await waitForWeb();
  }
  if (!currentStatus) throw new Error("状态不可用");
  window.location.href = currentStatus.panelURL;
}

async function handleAction(action: string): Promise<void> {
  if (busy) return;
  if (action === "migrate-legacy" && !window.confirm("迁移旧模块身份？\n旧模块须已禁用或移除，且旧、新运行时均已停止；新身份必须不存在。旧文件将保留，迁移后等待单独启用。")) return;
  if (action === "apply-staged" && !window.confirm("应用暂存运行时？\n当前运行时将停止并切换至已验证的暂存版本。此操作更新运行时，不更新当前管理器中的 WebUI，也不重启设备。")) return;
  setBusy(true);
  announce("处理中");
  try {
    switch (action) {
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
          "migration-incomplete": "迁移未完成", "awaiting-enable": "已迁移，待启用",
          "destination-exists": "新模块身份已存在", "migration-required": "待迁移",
          "no-legacy-identity": "未发现旧身份",
        };
        const data: unknown = JSON.parse(await execute("migration-status"));
        if (!data || typeof data !== "object" || !("state" in data) || typeof data.state !== "string" || !Object.hasOwn(labels, data.state)) throw new Error("Invalid migration status");
        announce(labels[data.state]!);
        break;
      }
      case "copy-ip":
        if (currentStatus?.ipv4) {
          await navigator.clipboard.writeText(currentStatus.ipv4);
          announce("Tailscale IP 已复制");
          toast("Tailscale IP 已复制");
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
      renderMessage(root, "状态不可用", errorMessage(error));
      drawIcons();
    }
    announce(errorMessage(error), true);
  } finally {
    setBusy(false);
  }
}

root.addEventListener("click", (event) => {
  const button = (event.target as Element).closest<HTMLButtonElement>("button[data-action]");
  if (button?.dataset.action) void handleAction(button.dataset.action);
});

renderMessage(root, "正在读取状态", "请稍候");
drawIcons();
void handleAction("refresh");
