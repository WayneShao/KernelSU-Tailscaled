import {
  ArrowLeft,
  Circle,
  Copy,
  createIcons,
  ExternalLink,
  Power,
  PowerOff,
  RefreshCw,
  RotateCw,
  ScrollText,
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

function drawIcons(): void {
  createIcons({
    icons: { ArrowLeft, Circle, Copy, ExternalLink, Power, PowerOff, RefreshCw, RotateCw, ScrollText },
    attrs: { "stroke-width": 2, width: 18, height: 18 },
  });
}

function setBusy(value: boolean): void {
  busy = value;
  root.querySelectorAll<HTMLButtonElement>("button").forEach((button) => {
    button.disabled = value || button.disabled;
  });
  root.setAttribute("aria-busy", String(value));
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

async function execute(action: ModuleAction): Promise<string> {
  const result = await runAction(action);
  if (result.exitCode !== 0) {
    throw new Error(result.stderr.trim() || result.stdout.trim() || `命令失败 (${result.exitCode})`);
  }
  return result.stdout;
}

async function refreshStatus(): Promise<void> {
  setBusy(true);
  try {
    currentStatus = parseRuntimeStatus(await execute("status-json"));
    renderDashboard(root, currentStatus);
    drawIcons();
  } catch (error) {
    renderMessage(root, "状态不可用", errorMessage(error));
    drawIcons();
  } finally {
    setBusy(false);
  }
}

async function showLogs(): Promise<void> {
  setBusy(true);
  try {
    renderLogs(root, await execute("logs"));
    drawIcons();
  } catch (error) {
    renderMessage(root, "日志不可用", errorMessage(error), "logs");
    drawIcons();
  } finally {
    setBusy(false);
  }
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function waitForWeb(): Promise<void> {
  for (let attempt = 0; attempt < 12; attempt += 1) {
    const status = parseRuntimeStatus(await execute("status-json"));
    if (status.components.web === "running") return;
    await delay(500);
  }
  throw new Error("本地面板未在限定时间内启动");
}

async function openPanel(): Promise<void> {
  setBusy(true);
  try {
    if (currentStatus?.components.web !== "running") {
      await execute("web-restart");
      await waitForWeb();
    }
    window.location.href = "http://127.0.0.1:8088/";
  } catch (error) {
    renderMessage(root, "面板启动失败", errorMessage(error), "open-panel");
    drawIcons();
    setBusy(false);
  }
}

async function handleAction(action: string): Promise<void> {
  if (busy) return;
  switch (action) {
    case "refresh":
    case "back":
      await refreshStatus();
      return;
    case "logs":
    case "refresh-logs":
      await showLogs();
      return;
    case "copy-ip":
      if (currentStatus?.ipv4) {
        await navigator.clipboard.writeText(currentStatus.ipv4);
        toast("Tailscale IP 已复制");
      }
      return;
    case "open-panel":
      await openPanel();
      return;
    case "enable":
    case "disable":
    case "restart":
      setBusy(true);
      try {
        await execute(action);
        await refreshStatus();
      } catch (error) {
        renderMessage(root, "操作失败", errorMessage(error));
        drawIcons();
        setBusy(false);
      }
      return;
  }
}

root.addEventListener("click", (event) => {
  const button = (event.target as Element).closest<HTMLButtonElement>("button[data-action]");
  if (button?.dataset.action) void handleAction(button.dataset.action);
});

renderMessage(root, "正在读取状态", "请稍候");
drawIcons();
void refreshStatus();
