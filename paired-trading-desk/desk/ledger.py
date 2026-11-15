"""Append-only hash chain. State is derived from the file, never edited in place."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _digest(previous: str, event: dict) -> str:
    payload = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256((previous + payload).encode("utf-8")).hexdigest()


def append_events(path: Path, events: list[dict]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    previous = "0" * 64
    if path.exists():
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if lines:
            previous = json.loads(lines[-1])["hash"]
    written = previous
    with path.open("a", encoding="utf-8") as handle:
        for event in events:
            written = _digest(previous, event)
            record = {"prev": previous, "hash": written, "event": event}
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            previous = written
    return written


def verify(path: Path) -> int:
    if not path.exists():
        return 0
    previous = "0" * 64
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        expected = _digest(previous, record["event"])
        if record["prev"] != previous or record["hash"] != expected:
            raise ValueError(f"rantai ledger rusak pada baris {count + 1}")
        previous = record["hash"]
        count += 1
    return count


def read_events(path: Path) -> list[dict]:
    verify(path)
    events: list[dict] = []
    if not path.exists():
        return events
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line)["event"])
    return events
