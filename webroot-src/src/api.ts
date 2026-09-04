import { exec } from "kernelsu";

export type ModuleAction =
  | "status-json"
  | "enable"
  | "disable"
  | "restart"
  | "logs"
  | "web-restart";

export interface CommandResult {
  stdout: string;
  stderr: string;
  exitCode: number;
}

const SERVICE = "/data/adb/modules/magisk-tailscaled/tailscale/scripts/tailscale-service";
const ACTIONS: ReadonlySet<string> = new Set([
  "status-json",
  "enable",
  "disable",
  "restart",
  "logs",
  "web-restart",
]);

export function commandFor(action: ModuleAction): string {
  if (!ACTIONS.has(action)) {
    throw new Error("Unsupported action");
  }
  return `${SERVICE} ${action}`;
}

export async function runAction(action: ModuleAction): Promise<CommandResult> {
  const result = await exec(commandFor(action));
  return {
    stdout: String(result.stdout ?? ""),
    stderr: String(result.stderr ?? ""),
    exitCode: Number(result.errno),
  };
}
