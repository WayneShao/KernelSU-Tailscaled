import type { ComponentState, Lifecycle, RuntimeStatus } from "./model";

const lifecycleLabels: Record<Lifecycle, string> = {
  disabled: "已禁用", stopped: "已停止", starting: "启动中", running: "运行中",
  degraded: "降级", failed: "失败", "migration-required": "待迁移",
};

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
  if (value === null) return "未知";
  return value ? "接受" : "不接受";
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
  appendText(row, "span", state === "running" ? "运行中" : state === "stopped" ? "已停止" : "未知", "component-value");
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
  appendText(header, "p", status.hostname ?? "设备名称未知", "device-name");
  const state = appendText(header, "p", `${lifecycleLabels[status.lifecycle]} · ${status.backendState}`, "backend-state");
  state.dataset.lifecycle = status.lifecycle;
  root.append(header);

  const actions = document.createElement("nav");
  actions.className = "primary-actions";
  actions.setAttribute("aria-label", "运行控制");
  const migrationRequired = status.lifecycle === "migration-required" || status.diagnostics.some((item) => item.code === "migration-required");
  const awaitingEnable = status.diagnostics.some((item) => item.code === "migration-awaiting-enable");
  const enable = !status.enabled || awaitingEnable;
  if (!migrationRequired) addButton(actions, enable ? "enable" : "disable", enable ? "启用" : "禁用", enable ? "启用 Tailscale" : "禁用 Tailscale");
  addButton(actions, "refresh", "刷新", "刷新状态");
  addButton(actions, "copy-ip", "复制 IP", "复制 Tailscale IPv4 地址").disabled = status.ipv4 === null;
  addButton(actions, "restart", "重启服务", "重启 Tailscale 模块服务").disabled = !status.enabled || migrationRequired || awaitingEnable;
  root.append(actions);

  const updateControls = document.createElement("section");
  appendText(updateControls, "h2", "更新控制");
  const updateFacts = document.createElement("dl");
  addFact(updateFacts, "当前运行时", status.runtime.activeVersion ?? "未知");
  addFact(updateFacts, "待应用版本", status.runtime.stagedVersion ?? "无");
  updateControls.append(updateFacts);
  if (status.runtime.stagedVersion) {
    appendText(updateControls, "p", "更新已暂存；模块文件将在 Android 重启后完成切换。", "notice");
    addButton(updateControls, "apply-staged", "应用暂存更新", "应用暂存更新");
  }
  root.append(updateControls);

  if (migrationRequired || status.diagnostics.length > 0 || status.health.length > 0) {
    const warnings = document.createElement("section");
    warnings.className = "diagnostics";
    appendText(warnings, "h2", "诊断");
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
    if (migrationRequired) addButton(warnings, "migrate-legacy", "迁移旧身份", "迁移旧模块身份");
    root.append(warnings);
  }

  const network = document.createElement("section");
  appendText(network, "h2", "网络");
  const facts = document.createElement("dl");
  addFact(facts, "模块启用意图", status.enabled ? "已启用" : "已禁用");
  addFact(facts, "Tailscale IPv4", valueOrDash(status.ipv4));
  addFact(facts, "运行模式", status.mode === "native" ? "Native TUN" : "Userspace");
  addFact(facts, "接受路由", preference(status.acceptRoutes));
  addFact(facts, "接受 DNS", preference(status.acceptDNS));
  addFact(facts, "出口节点", valueOrDash(status.exitNode));
  network.append(facts);
  root.append(network);

  const health = document.createElement("section");
  appendText(health, "h2", "组件");
  const components = document.createElement("div");
  components.className = "component-list";
  addComponent(components, "Supervisor", status.components.supervisor);
  addComponent(components, "tailscaled", status.components.daemon);
  addComponent(components, "数据平面", status.components.dataPlane);
  addComponent(components, "本地面板", status.components.web);
  health.append(components);
  root.append(health);

  const versions = document.createElement("section");
  appendText(versions, "h2", "版本");
  const versionFacts = document.createElement("dl");
  addFact(versionFacts, "模块", status.moduleVersion);
  addFact(versionFacts, "Tailscale", status.tailscaleVersion);
  addFact(versionFacts, "活动运行时", status.runtime.activeVersion ?? "未知");
  addFact(versionFacts, "待应用运行时", status.runtime.stagedVersion ?? "无");
  addFact(versionFacts, "上一运行时", status.runtime.previousVersion ?? "无");
  versions.append(versionFacts);
  root.append(versions);

  const secondary = document.createElement("nav");
  secondary.className = "secondary-actions";
  secondary.setAttribute("aria-label", "详情操作");
  addButton(secondary, "logs", "日志", "查看最近日志");
  addButton(secondary, "diagnostics", "诊断记录", "查看诊断记录");
  addButton(secondary, "migration-status", "迁移状态", "查看迁移状态");
  addButton(secondary, "open-panel", "打开完整面板", "打开 Tailscale 完整面板").disabled = migrationRequired || awaitingEnable;
  root.append(secondary);
}

export function renderLogs(root: HTMLElement, logs: string, kind: "logs" | "diagnostics" = "logs"): void {
  root.replaceChildren();
  const header = document.createElement("header");
  appendText(header, "p", "KernelSU-Tailscaled", "eyebrow");
  appendText(header, "h1", kind === "logs" ? "运行日志" : "诊断记录");
  root.append(header);
  const pre = document.createElement("pre");
  pre.textContent = logs || "暂无日志";
  root.append(pre);
  const actions = document.createElement("nav");
  actions.className = "secondary-actions";
  addButton(actions, kind === "logs" ? "refresh-logs" : "refresh-diagnostics", "刷新", "刷新记录");
  addButton(actions, "back", "返回", "返回状态页");
  root.append(actions);
}

export function renderMessage(root: HTMLElement, title: string, message: string, retryAction = "refresh"): void {
  root.replaceChildren();
  const header = document.createElement("header");
  appendText(header, "p", "KernelSU-Tailscaled", "eyebrow");
  appendText(header, "h1", title);
  root.append(header);
  appendText(root, "p", message, "message");
  const actions = document.createElement("nav");
  actions.className = "secondary-actions";
  addButton(actions, retryAction, "重试", "重试当前操作");
  if (retryAction !== "refresh") addButton(actions, "back", "返回", "返回状态页");
  root.append(actions);
}
