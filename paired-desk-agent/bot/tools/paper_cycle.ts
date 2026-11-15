import { defineTool } from "@grok/agent-sdk/tools";
import * as z from "zod/v4";
import { deskCommand } from "../lib/desk.ts";

export default defineTool({
  description:
    "Replay the paired desk paper book from the fixtures. Resets the agent paper session. Does not send a live order.",
  effect: "idempotent",
  inputSchema: z.object({}),
  async execute() {
    return deskCommand("cycle");
  },
});
