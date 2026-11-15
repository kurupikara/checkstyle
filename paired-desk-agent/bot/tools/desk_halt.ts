import { defineTool } from "@grok/agent-sdk/tools";
import * as z from "zod/v4";
import { deskCommand } from "../lib/desk.ts";

export default defineTool({
  description: "Turn on the paper-desk kill switch so the next cycle fills nothing.",
  effect: "idempotent",
  inputSchema: z.object({
    reason: z.string().min(1).max(200),
  }),
  async execute({ reason }) {
    return deskCommand("halt", [reason]);
  },
});
