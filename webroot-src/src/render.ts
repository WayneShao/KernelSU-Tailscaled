import type { ComponentState, Lifecycle, RuntimeStatus } from "./model";
import type { EngineStatus } from './engine';
import { appendLanguageSelector, t } from "./i18n";
import { renderServerSettings } from "./server";

function lifecycleLabel(lifecycle: Lifecycle): string {
  const labels: Record<Lifecycle, string> = {
    disabled: t("Disabled", "已禁用"), stopped: t("Stopped", "已停止"), starting: t("Starting", "启动中"), running: t("Running", "运行中"),
    degraded: t("Degraded", "降级"), failed: t("Failed", "失败"), "migration-required": t("Migration required", "待迁移"),
  };
  return labels[lifecycle];
}

function appendText(parent: HTMLElement, tagName: keyof HTMLElementTagNameMap, text: string, className?: string): HTMLElement {
  const element = document.createElement(tagName);
  element.textContent = text;
  if (className) element.className = className;
  parent.append(element);
  return element;
}

function valueOrDash(value: string | null): string {
  return value && value.length > 0 ? value : "--";
}

function preference(value: boolean | null): string {
  if (value === null) return t("Unknown", "未知");
  return value ? t("Accepted", "接受") : t("Not accepted", "不接受");
}

function addFact(parent: HTMLElement, label: string, value: string): void {
  const row = document.createElement("div");
  row.className = "fact-row";
  appendText(row, "dt", label);
  appendText(row, "dd", value);
  parent.append(row);
}

function addComponent(parent: HTMLElement, label: string, state: ComponentState): void {
  const row = document.createElement("div");
  row.className = "component-row";
  row.dataset.state = state;
  appendText(row, "span", label);
  appendText(row, "span", state === "running" ? t("Running", "运行中") : state === "stopped" ? t("Stopped", "已停止") : t("Unknown", "未知"), "component-value");
  parent.append(row);
}

function addButton(parent: HTMLElement, action: string, label: string, title: string): HTMLButtonElement {
  const icons: Record<string, string> = {
    enable: "power",
    disable: "power-off",
    refresh: "refresh-cw",
    "copy-ip": "copy",
    restart: "rotate-cw",
    logs: "scroll-text",
    "refresh-logs": "refresh-cw",
    back: "arrow-left",
    "open-panel": "external-link",
    diagnostics: "stethoscope",
    "refresh-diagnostics": "refresh-cw",
    "migration-status": "list-checks",
    "migrate-legacy": "import",
    "apply-staged": "package-check",
  };
  const button = document.createElement("button");
  button.type = "button";
  button.dataset.action = action;
  button.title = title;
  button.setAttribute("aria-label", title);
  const icon = document.createElement("i");
  icon.setAttribute("data-lucide", icons[action] ?? "circle");
  icon.setAttribute("aria-hidden", "true");
  button.append(icon);
  const iconOnly = ["refresh", "copy-ip", "restart", "refresh-logs", "refresh-diagnostics"].includes(action);
  if (iconOnly) button.className = "icon-button";
  appendText(button, "span", label, iconOnly ? "visually-hidden" : undefined);
  parent.append(button);
  return button;
}

export function renderDashboard(root: HTMLElement, status: RuntimeStatus): void {
  root.replaceChildren();

  const header = document.createElement("header");
  appendText(header, "h1", "KernelSU-Tailscaled");
  appendText(header, "p", status.hostname ?? t("Unknown device", "设备名称未知"), "device-name");
  const backendLabels: Record<string, string> = {
    NeedsLogin: t("Sign-in required", "需要登录"), NeedsMachineAuth: t("Device approval required", "需要批准设备"),
    Running: t("Connected", "已连接"), Stopped: t("Stopped", "已停止"), Starting: t("Starting", "启动中"),
    NoState: t("Not configured", "尚未配置"), Unknown: t("Unknown", "未知"),
  };
  const state = appendText(header, "p", `${lifecycleLabel(status.lifecycle)} · ${backendLabels[status.backendState] ?? status.backendState}`, "backend-state");
  state.dataset.lifecycle = status.lifecycle;
  appendLanguageSelector(header);
  root.append(header);

  const actions = document.createElement("nav");
  actions.className = "primary-actions";
  actions.setAttribute("aria-label", t("Runtime controls", "运行控制"));
  const migrationRequired = status.lifecycle === "migration-required" || status.diagnostics.some((item) => item.code === "migration-required");
  const awaitingEnable = status.diagnostics.some((item) => item.code === "migration-awaiting-enable");
  const enable = !status.enabled || awaitingEnable;
  if (!migrationRequired) addButton(actions, enable ? "enable" : "disable", enable ? t("Enable", "启用") : t("Disable", "禁用"), enable ? t("Enable Tailscale", "启用 Tailscale") : t("Disable Tailscale", "禁用 Tailscale"));
  addButton(actions, "refresh", t("Refresh", "刷新"), t("Refresh status", "刷新状态"));
  addButton(actions, "copy-ip", t("Copy IP", "复制 IP"), t("Copy Tailscale IPv4 address", "复制 Tailscale IPv4 地址")).disabled = status.ipv4 === null;
  addButton(actions, "restart", t("Restart service", "重启服务"), t("Restart Tailscale module service", "重启 Tailscale 模块服务")).disabled = !status.enabled || migrationRequired || awaitingEnable;
  root.append(actions);
  renderServerSettings(root, status);

  const updateControls = document.createElement("section");
  appendText(updateControls, "h2", t("Updates", "更新控制"));
  const updateFacts = document.createElement("dl");
  addFact(updateFacts, t("Current runtime", "当前运行时"), status.runtime.activeVersion ?? t("Unknown", "未知"));
  addFact(updateFacts, t("Staged version", "待应用版本"), status.runtime.stagedVersion ?? t("None", "无"));
  updateControls.append(updateFacts);
  addButton(updateControls, 'engine-page', t("Tailscale engine update", "Tailscale 引擎更新"), t("Check and update the official Tailscale engine", "检查和更新官方 Tailscale 引擎"));
  if (status.runtime.stagedVersion) {
    appendText(updateControls, "p", t("An update is staged; module files will switch after Android restarts.", "更新已暂存；模块文件将在 Android 重启后完成切换。"), "notice");
    addButton(updateControls, "apply-staged", t("Apply staged update", "应用暂存更新"), t("Apply staged update", "应用暂存更新"));
  }
  root.append(updateControls);

  if (migrationRequired || status.diagnostics.length > 0 || status.health.length > 0) {
    const warnings = document.createElement("section");
    warnings.className = "diagnostics";
    appendText(warnings, "h2", t("Diagnostics", "诊断"));
    for (const diagnostic of status.diagnostics) {
      const item = document.createElement("div");
      item.className = "diagnostic";
      item.dataset.severity = diagnostic.severity;
      appendText(item, "span", diagnostic.code, "diagnostic-code");
      appendText(item, "p", diagnostic.message);
      warnings.append(item);
    }
    for (const message of status.health) {
      const item = appendText(warnings, "p", message, "upstream-health");
      item.dataset.severity = "warning";
    }
    if (migrationRequired) addButton(warnings, "migrate-legacy", t("Migrate legacy identity", "迁移旧身份"), t("Migrate legacy module identity", "迁移旧模块身份"));
    root.append(warnings);
  }

  const network = document.createElement("section");
  appendText(network, "h2", t("Network", "网络"));
  const facts = document.createElement("dl");
  addFact(facts, t("Module enabled", "模块启用意图"), status.enabled ? t("Enabled", "已启用") : t("Disabled", "已禁用"));
  addFact(facts, "Tailscale IPv4", valueOrDash(status.ipv4));
  addFact(facts, t("Runtime mode", "运行模式"), status.mode === "native" ? "Native TUN" : "Userspace");
  addFact(facts, t("Accept routes", "接受路由"), preference(status.acceptRoutes));
  addFact(facts, t("Accept DNS", "接受 DNS"), preference(status.acceptDNS));
  addFact(facts, t("Exit node", "出口节点"), valueOrDash(status.exitNode));
  network.append(facts);
  root.append(network);

  const health = document.createElement("section");
  appendText(health, "h2", t("Components", "组件"));
  const components = document.createElement("div");
  components.className = "component-list";
  addComponent(components, "Supervisor", status.components.supervisor);
  addComponent(components, "tailscaled", status.components.daemon);
  addComponent(components, t("Data plane", "数据平面"), status.components.dataPlane);
  addComponent(components, t("Local panel", "本地面板"), status.components.web);
  health.append(components);
  root.append(health);

  const versions = document.createElement("section");
  appendText(versions, "h2", t("Versions", "版本"));
  const versionFacts = document.createElement("dl");
  addFact(versionFacts, t("Module", "模块"), status.moduleVersion);
  addFact(versionFacts, "Tailscale", status.tailscaleVersion);
  addFact(versionFacts, t("Active runtime", "活动运行时"), status.runtime.activeVersion ?? t("Unknown", "未知"));
  addFact(versionFacts, t("Staged runtime", "待应用运行时"), status.runtime.stagedVersion ?? t("None", "无"));
  addFact(versionFacts, t("Previous runtime", "上一运行时"), status.runtime.previousVersion ?? t("None", "无"));
  versions.append(versionFacts);
  root.append(versions);

  const secondary = document.createElement("nav");
  secondary.className = "secondary-actions";
  secondary.setAttribute("aria-label", t("Details actions", "详情操作"));
  addButton(secondary, "logs", t("Logs", "日志"), t("View recent logs", "查看最近日志"));
  addButton(secondary, "diagnostics", t("Diagnostic records", "诊断记录"), t("View diagnostic records", "查看诊断记录"));
  addButton(secondary, "migration-status", t("Migration status", "迁移状态"), t("View migration status", "查看迁移状态"));
  addButton(secondary, "open-panel", t("Open full panel", "打开完整面板"), t("Open full Tailscale panel", "打开 Tailscale 完整面板")).disabled = migrationRequired || awaitingEnable;
  root.append(secondary);
}

export function renderEngineUpdate(root: HTMLElement, status: EngineStatus): void {
  root.replaceChildren();
  const header = document.createElement('header');
  appendText(header, 'h1', t("Tailscale engine update", "Tailscale 引擎更新"));
  appendLanguageSelector(header);
  root.append(header);
  const section = document.createElement('section');
  const facts = document.createElement('dl');
  addFact(facts, t("Current engine", "当前引擎"), status.current || t("Unknown", "未知"));
  addFact(facts, t("Official stable release", "官方稳定版"), status.latest || t("Not checked", "尚未检查"));
  addFact(facts, t("Verified and ready to install", "已校验待安装"), status.staged || t("None", "无"));
  section.append(facts);
  appendText(section, 'p', t("Downloaded from Tailscale and verified. Applying briefly restarts the service, retaining your login and settings. No device reboot needed.", "从 Tailscale 官方下载并校验。应用更新会短暂重启服务，保留登录和配置；设备无需重启。"));
  addButton(section, 'engine-check', t("Check for updates", "检查更新"), t("Check the official stable release", "检查官方稳定版"));
  if (status.latest) addButton(section, 'engine-prepare',
    status.latest === status.current ? t("Download and verify again", "重新下载并校验") : t("Download and verify", "下载并校验"), t("Download and verify the official engine", "下载并校验官方引擎"));
  if (status.staged) addButton(section, 'engine-apply', t("Apply engine update", "应用引擎更新"), t("Apply verified engine", "应用已校验引擎"));
  addButton(section, 'back', t("Back", "返回"), t("Back to status", "返回状态页"));
  root.append(section);
}

export function renderLogs(root: HTMLElement, logs: string, kind: "logs" | "diagnostics" = "logs"): void {
  root.replaceChildren();
  const header = document.createElement("header");
  appendText(header, "p", "KernelSU-Tailscaled", "eyebrow");
  appendText(header, "h1", kind === "logs" ? t("Runtime logs", "运行日志") : t("Diagnostic records", "诊断记录"));
  appendLanguageSelector(header);
  root.append(header);
  const pre = document.createElement("pre");
  pre.textContent = logs || t("No logs yet", "暂无日志");
  root.append(pre);
  const actions = document.createElement("nav");
  actions.className = "secondary-actions";
  addButton(actions, kind === "logs" ? "refresh-logs" : "refresh-diagnostics", t("Refresh", "刷新"), t("Refresh records", "刷新记录"));
  addButton(actions, "back", t("Back", "返回"), t("Back to status", "返回状态页"));
  root.append(actions);
}

export function renderMessage(root: HTMLElement, title: string, message: string, retryAction = "refresh"): void {
  root.replaceChildren();
  const header = document.createElement("header");
  appendText(header, "p", "KernelSU-Tailscaled", "eyebrow");
  appendText(header, "h1", title);
  appendLanguageSelector(header);
  root.append(header);
  appendText(root, "p", message, "message");
  const actions = document.createElement("nav");
  actions.className = "secondary-actions";
  addButton(actions, retryAction, t("Retry", "重试"), t("Retry current operation", "重试当前操作"));
  if (retryAction !== "refresh") addButton(actions, "back", t("Back", "返回"), t("Back to status", "返回状态页"));
  root.append(actions);
}
