import { defineTool } from "@grok/agent-sdk/tools";
import * as z from "zod/v4";
import { deskCommand } from "../lib/desk.ts";

export default defineTool({
  description: "Read the latest paired-desk paper report. Does not trade.",
  effect: "read",
  inputSchema: z.object({}),
  async execute() {
    return deskCommand("status");
  },
});
