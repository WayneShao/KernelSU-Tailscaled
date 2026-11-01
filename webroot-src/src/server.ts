import { t } from "./i18n";
import type { RuntimeStatus } from "./model";

export const DEFAULT_CONTROL_URL = "https://controlplane.tailscale.com";

export function controlURL(value: string): string {
  const input = value.trim() || DEFAULT_CONTROL_URL;
  if (input.length > 2048 || !/^https?:\/\/(?:[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?|\[[0-9a-fA-F:]+\])(?::[0-9]{1,5})?(?:\/[a-zA-Z0-9._~%/-]*)?$/.test(input)) {
    throw new Error(t("Enter an HTTP or HTTPS server URL without credentials, query, or fragment.", "请输入 HTTP 或 HTTPS 服务器地址，不含凭据、查询参数或片段。"));
  }
  try { new URL(input); } catch { throw new Error(t("Invalid server URL or port.", "服务器地址或端口无效。")); }
  return input.replace(/\/+$/, "");
}

export interface LoginResult { controlURL: string; authURL: string }

export function parseLoginResult(text: string): LoginResult {
  const data: unknown = JSON.parse(text);
  if (!data || typeof data !== "object" || !("controlURL" in data) || typeof data.controlURL !== "string" || !("authURL" in data) || typeof data.authURL !== "string") {
    throw new Error(t("Invalid sign-in response", "登录响应格式错误"));
  }
  const server = controlURL(data.controlURL);
  if (data.authURL) {
    const url = new URL(data.authURL);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) throw new Error(t("Invalid sign-in URL", "登录链接无效"));
  }
  return { controlURL: server, authURL: data.authURL };
}

export function renderServerSettings(root: HTMLElement, status: RuntimeStatus): void {
  const section = document.createElement("section");
  section.className = "server-settings";
  const title = document.createElement("h2");
  title.textContent = t("Sign in / Headscale", "登录 / Headscale");
  const form = document.createElement("form");
  form.dataset.server = "";
  const label = document.createElement("label");
  label.htmlFor = "login-server";
  label.textContent = t("Control server URL", "控制服务器地址");
  const input = document.createElement("input");
  input.id = "login-server";
  input.name = "server";
  input.type = "url";
  input.maxLength = 2048;
  input.autocomplete = "off";
  input.spellcheck = false;
  input.placeholder = "https://headscale.example.com";
  input.value = status.controlURL ?? "";
  input.setAttribute("aria-describedby", "server-help");
  const help = document.createElement("p");
  help.id = "server-help";
  help.className = "message";
  help.textContent = t("Use your Headscale base URL, or leave blank for Tailscale. HTTPS is recommended; HTTP is unencrypted. Changing servers disconnects the current network and requires registration with the new server.", "填写 Headscale 基础地址，留空则使用 Tailscale。建议使用 HTTPS；HTTP 未加密。切换服务器将断开当前网络，并需在新服务器注册。");
  const submit = document.createElement("button");
  submit.type = "submit";
  submit.textContent = t("Connect / sign in", "连接 / 登录");
  const blocked = !status.enabled || status.components.daemon !== "running" || status.lifecycle === "migration-required" || status.diagnostics.some(item => ["migration-required", "migration-awaiting-enable"].includes(item.code));
  input.disabled = blocked;
  submit.disabled = blocked;
  form.append(label, input, help, submit);
  section.append(title, form);
  root.append(section);
}

export function renderLoginResult(root: HTMLElement, result: LoginResult): void {
  const section = root.querySelector(".server-settings");
  if (!section) return;
  const message = document.createElement("p");
  message.className = "message";
  message.setAttribute("role", "status");
  message.textContent = result.authURL
    ? t("Open the sign-in link and complete registration on your server, then refresh status.", "打开登录链接，在服务器完成注册后刷新状态。")
    : t("The server preference was saved. If sign-in is still pending, open the full panel to complete registration, then refresh status.", "服务器设置已保存。如仍需登录，请打开完整面板完成注册后刷新状态。");
  section.append(message);
  if (result.authURL) {
    const link = document.createElement("a");
    link.href = result.authURL;
    link.rel = "noreferrer noopener";
    link.className = "sign-in-link";
    link.textContent = t("Open sign-in link", "打开登录链接");
    section.append(link);
  }
}
