import { execFile } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const exec = promisify(execFile);

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

export function deskRoot(): string {
  if (process.env.PAIRED_DESK_ROOT) return process.env.PAIRED_DESK_ROOT;
  const project = path.resolve(fileURLToPath(new URL(".", import.meta.url)), "../..");
  return path.resolve(project, "../paired-trading-desk");
}

export async function deskCommand(command: string, extra: string[] = []): Promise<JsonValue> {
  const root = deskRoot();
  try {
    const { stdout } = await exec("python3", ["-m", "desk.agent_api", command, ...extra], {
      cwd: root,
      timeout: 30_000,
    });
    return JSON.parse(stdout) as JsonValue;
  } catch (error) {
    const message = error instanceof Error ? error.message : "desk gagal";
    return { error: message, deskRoot: root };
  }
}
