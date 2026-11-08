import { t } from "./i18n";
import type { RuntimeStatus } from "./model";

export function taildropDirectory(value: string): string {
  const sharedPath = /^\/sdcard\/.+/s.test(value) || /^\/storage\/(?:emulated\/[0-9]+|self\/primary|(?!(?:emulated|self)(?:\/|$))[A-Za-z0-9_-]+)\/.+/s.test(value);
  if (!sharedPath || /[\u0000-\u001f\u007f-\u009f]/.test(value) || value.split("/").slice(1).some((part) => !part || part === "." || part === "..")) {
    throw new Error(t("Enter a shared-storage folder such as /sdcard/Download or /storage/emulated/0/Download. Do not use mount roots, empty or . / .. segments, trailing slashes, or control characters.", "请输入共享存储文件夹，例如 /sdcard/Download 或 /storage/emulated/0/Download。不可使用挂载根目录、空路径段、. / .. 路径段、末尾斜杠或控制字符。"));
  }
  return value;
}

export function renderTaildropSettings(root: HTMLElement, status: RuntimeStatus["taildrop"]): void {
  const section = document.createElement("section");
  section.className = "taildrop-settings";
  const title = document.createElement("h2");
  title.textContent = "Taildrop";
  const receiver = document.createElement("div");
  receiver.className = "component-row";
  receiver.dataset.state = status.receiver;
  const receiverLabel = document.createElement("span");
  receiverLabel.textContent = t("Receiver", "接收器");
  const receiverValue = document.createElement("span");
  receiverValue.className = "component-value";
  receiverValue.textContent = status.receiver === "running" ? t("Running", "运行中") : status.receiver === "stopped" ? t("Stopped", "已停止") : t("Unknown", "未知");
  receiver.append(receiverLabel, receiverValue);
  const form = document.createElement("form");
  form.dataset.taildrop = "";
  const label = document.createElement("label");
  label.htmlFor = "taildrop-directory";
  label.textContent = t("Destination folder", "保存文件夹");
  const input = document.createElement("input");
  input.id = "taildrop-directory";
  input.name = "directory";
  input.type = "text";
  input.required = true;
  input.autocomplete = "off";
  input.autocapitalize = "off";
  input.spellcheck = false;
  input.placeholder = "/sdcard/Download";
  input.value = status.directory;
  input.setAttribute("aria-describedby", "taildrop-help");
  const help = document.createElement("p");
  help.id = "taildrop-help";
  help.className = "message";
  help.textContent = t("Automatically saves received files while the module runs. Use a folder under /sdcard/ or /storage/; it will be created if needed. Duplicate names are numbered, never overwritten. On errors, files remain in the private inbox; check Logs and Diagnostic records.", "模块运行时自动保存收到的文件。请选择 /sdcard/ 或 /storage/ 下的文件夹，不存在时会自动创建。同名文件会编号保存，不会覆盖。出错时文件会保留在私有收件箱，请查看日志和诊断记录。");
  const submit = document.createElement("button");
  submit.type = "submit";
  submit.textContent = t("Save folder", "保存文件夹");
  form.append(label, input, help, submit);
  section.append(title, receiver, form);
  root.append(section);
}
