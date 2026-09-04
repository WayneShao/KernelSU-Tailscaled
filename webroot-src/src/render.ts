import type { ComponentState, RuntimeStatus } from "./model";

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
  appendText(row, "span", state === "running" ? "运行中" : "已停止", "component-value");
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
  };
  const button = document.createElement("button");
  button.type = "button";
  button.dataset.action = action;
  button.title = title;
  const icon = document.createElement("i");
  icon.setAttribute("data-lucide", icons[action] ?? "circle");
  icon.setAttribute("aria-hidden", "true");
  button.append(icon);
  appendText(button, "span", label);
  parent.append(button);
  return button;
}

export function renderDashboard(root: HTMLElement, status: RuntimeStatus): void {
  root.replaceChildren();

  const header = document.createElement("header");
  appendText(header, "p", "TAILSCALE", "eyebrow");
  appendText(header, "h1", valueOrDash(status.hostname));
  const state = appendText(header, "p", status.enabled ? status.backendState : "已禁用", "backend-state");
  state.dataset.connected = String(status.backendState === "Running");
  root.append(header);

  const actions = document.createElement("nav");
  actions.className = "primary-actions";
  actions.setAttribute("aria-label", "模块操作");
  addButton(actions, status.enabled ? "disable" : "enable", status.enabled ? "禁用" : "启用", status.enabled ? "禁用 Tailscale" : "启用 Tailscale");
  addButton(actions, "refresh", "刷新", "刷新状态");
  addButton(actions, "copy-ip", "复制 IP", "复制 Tailscale IPv4 地址").disabled = status.ipv4 === null;
  addButton(actions, "restart", "重启服务", "重启 Tailscale 模块服务").disabled = !status.enabled;
  root.append(actions);

  const network = document.createElement("section");
  appendText(network, "h2", "网络");
  const facts = document.createElement("dl");
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
  versions.append(versionFacts);
  root.append(versions);

  const secondary = document.createElement("nav");
  secondary.className = "secondary-actions";
  secondary.setAttribute("aria-label", "详情操作");
  addButton(secondary, "logs", "日志", "查看最近日志");
  addButton(secondary, "open-panel", "打开完整面板", "打开 Tailscale 完整面板");
  root.append(secondary);
}

export function renderLogs(root: HTMLElement, logs: string): void {
  root.replaceChildren();
  const header = document.createElement("header");
  appendText(header, "p", "TAILSCALE", "eyebrow");
  appendText(header, "h1", "运行日志");
  root.append(header);
  const pre = document.createElement("pre");
  pre.textContent = logs || "暂无日志";
  root.append(pre);
  const actions = document.createElement("nav");
  actions.className = "secondary-actions";
  addButton(actions, "refresh-logs", "刷新", "刷新日志");
  addButton(actions, "back", "返回", "返回状态页");
  root.append(actions);
}

export function renderMessage(root: HTMLElement, title: string, message: string, retryAction = "refresh"): void {
  root.replaceChildren();
  const header = document.createElement("header");
  appendText(header, "p", "TAILSCALE", "eyebrow");
  appendText(header, "h1", title);
  root.append(header);
  appendText(root, "p", message, "message");
  const actions = document.createElement("nav");
  actions.className = "secondary-actions";
  addButton(actions, retryAction, "重试", "重试当前操作");
  root.append(actions);
}
