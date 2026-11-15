---
name: paired-desk
description: Operate the paired paper trading desk. Use when asked to run, inspect, halt, or explain a cycle.
---

# Paired desk

The desk pairs five tools. Do not merge their jobs.

- Vibe-Trading researches and backtests. It does not send exchange orders.
- AI Hedge Fund votes on equities and keeps a paper book. It does not trade live.
- Hummingbot executes the crypto CEX sleeve. Paper mode uses `binance_paper_trade`.
- pumpfun-bonkfun-bot is the Solana launchpad sleeve. Leave its config `enabled: false` unless the user set live mode on purpose.
- You are the operator. Read the report, run the paper cycle, and stop at the kill switch. Do not invent wallet keys or pass secrets on a command line.

From `paired-trading-desk/`:

```bash
python3 paired-desk demo
python3 paired-desk status
python3 paired-desk doctor
python3 paired-desk halt --reason "berhenti"
python3 paired-desk resume
python3 paired-desk handoff
```

`demo` replays the fixtures from scratch and writes `var/demo/report.json`. A kill switch in that state directory blocks fills. Live execution is a separate command and refuses to run unless `desk.json` says `live` and `PAIRED_DESK_LIVE=I_UNDERSTAND`.
