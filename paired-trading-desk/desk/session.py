"""Persist a paper cycle and the kill switch. Nothing here sends a live order."""

from __future__ import annotations

import json
from pathlib import Path

from desk.config import ROOT, Config, load_config
from desk.engine import run_cycle
from desk.ledger import append_events, verify
from desk.market import load_fixture_book, load_launches
from desk.models import Bar


def state_dir(name: str, root: Path | None = None) -> Path:
    path = (root or ROOT) / "var" / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def reset_session(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for name in ("ledger.jsonl", "report.json"):
        file = path / name
        if file.exists():
            file.unlink()


def halt(path: Path, reason: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "KILL").write_text(reason.strip() + "\n", encoding="utf-8")


def resume(path: Path) -> bool:
    file = path / "KILL"
    if not file.exists():
        return False
    file.unlink()
    return True


def run_paper(
    path: Path,
    cfg: Config | None = None,
    series: dict[str, list[Bar]] | None = None,
    launches: list[dict] | None = None,
    reset: bool = False,
) -> dict:
    if reset:
        reset_session(path)
    config = cfg or load_config()
    report = run_cycle(
        config,
        series if series is not None else load_fixture_book(),
        launches if launches is not None else load_launches(),
        path,
    )
    events: list[dict] = []
    for fill in report["fills"]:
        events.append({"type": "fill", **fill})
    for launch in report["launches"]:
        events.append({"type": "launch", **launch})
    events.append(
        {
            "type": "session",
            "equity_usd": report["equity_usd"],
            "cash_usd": report["cash_usd"],
            "cash_sol": report["cash_sol"],
            "killed": report["killed"],
            "drawdown_halt": report["drawdown_halt"],
            "fills": len(report["fills"]),
        }
    )
    append_events(path / "ledger.jsonl", events)
    verify(path / "ledger.jsonl")
    (path / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


def load_report(path: Path) -> dict | None:
    file = path / "report.json"
    if not file.exists():
        return None
    return json.loads(file.read_text(encoding="utf-8"))
