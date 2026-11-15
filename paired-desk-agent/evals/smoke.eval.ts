import { defineEval, includes } from "@grok/agent-sdk/evals";

export default defineEval({
  tags: ["smoke"],
  description: "A paper cycle uses the desk tool and stays off live orders.",
  async test(t) {
    await t.send("Jalankan satu siklus paper dan sebut ekuitasnya.");
    t.succeeded();
    t.calledTool("paper_cycle");
    t.notCalledTool("desk_halt");
    t.check(t.reply, includes(/USD|paper|ekuitas/i));
  },
});
