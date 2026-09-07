import { exec } from "kernelsu";

export type ModuleAction =
  | "status-json"
  | "enable"
  | "disable"
  | "restart"
  | "logs"
  | "web-restart"
  | "diagnostics"
  | "migration-status"
  | "migrate-legacy"
  | "apply-staged";

export interface CommandResult {
  stdout: string;
  stderr: string;
  exitCode: number;
}

const SERVICE = "/data/adb/modules/kernelsu-tailscaled/control.sh";
const ACTIONS: ReadonlySet<string> = new Set([
  "status-json",
  "enable",
  "disable",
  "restart",
  "logs",
  "web-restart",
  "diagnostics",
  "migration-status",
  "migrate-legacy",
  "apply-staged",
]);

function deadlineFor(action: ModuleAction, remainingMs?: number): number {
  if (!ACTIONS.has(action)) {
    throw new Error("Unsupported action");
  }
  const maximum = ["status-json", "logs", "diagnostics", "migration-status"].includes(action) ? 40_000 : 90_000;
  if (remainingMs !== undefined && (!Number.isFinite(remainingMs) || remainingMs < 2_000)) {
    throw new Error("操作超时，请刷新状态确认结果");
  }
  return Math.min(remainingMs ?? maximum, maximum);
}

export function commandFor(action: ModuleAction, remainingMs?: number): string {
  const deadline = deadlineFor(action, remainingMs);
  // Leave time for the native callback after terminating a stalled shell command.
  const cushion = deadline >= 10_000 ? 5_000 : 1_000;
  const seconds = Math.max(1, Math.floor((deadline - cushion) / 1_000));
  return `/data/adb/ksu/bin/busybox timeout -s KILL ${seconds} sh ${SERVICE} ${action}`;
}

export async function runAction(action: ModuleAction, remainingMs?: number): Promise<CommandResult> {
  const deadline = deadlineFor(action, remainingMs);
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const expired = new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new Error(`操作超时 (${deadline / 1_000}s)，请刷新状态确认结果`)), deadline);
    });
    const result = await Promise.race([exec(commandFor(action, remainingMs)), expired]);
    return {
      stdout: String(result.stdout ?? ""),
      stderr: String(result.stderr ?? ""),
      exitCode: Number(result.errno),
    };
  } finally {
    clearTimeout(timer);
  }
}
