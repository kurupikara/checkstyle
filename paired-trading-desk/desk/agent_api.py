"""JSON entry for the paired-desk agent. Paper commands only."""

from __future__ import annotations

import json
import sys

from desk.session import halt, load_report, resume, run_paper, state_dir

STATE = "agent"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(json.dumps({"error": "perintah kosong"}))
        return 2
    command = args[0]
    path = state_dir(STATE)
    if command == "cycle":
        report = run_paper(path, reset=True)
    elif command == "status":
        report = load_report(path) or {"empty": True}
    elif command == "halt":
        reason = args[1] if len(args) > 1 and args[1].strip() else "dihentikan agent"
        halt(path, reason[:200])
        report = {"killed": reason[:200]}
    elif command == "resume":
        report = {"resumed": resume(path)}
    else:
        print(json.dumps({"error": f"perintah tidak dikenal: {command}"}))
        return 2
    json.dump(report, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
