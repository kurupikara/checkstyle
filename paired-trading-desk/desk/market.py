"""Bars and launch fixtures. Offline files are the default; Binance is optional."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from desk.config import ROOT
from desk.models import Bar


def load_bars(path: Path) -> list[Bar]:
    bars: list[Bar] = []
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        if not line.strip():
            continue
        date, close = line.split(",")
        bars.append(Bar(date, float(close)))
    if len(bars) < 2:
        raise ValueError(f"butuh minimal 2 bar di {path}")
    return bars


def load_fixture_book(directory: Path | None = None) -> dict[str, list[Bar]]:
    folder = directory or (ROOT / "fixtures" / "bars")
    book: dict[str, list[Bar]] = {}
    for path in sorted(folder.glob("*.csv")):
        book[path.stem] = load_bars(path)
    if not book:
        raise FileNotFoundError(f"tidak ada CSV di {folder}")
    return book


def load_launches(path: Path | None = None) -> list[dict]:
    file = path or (ROOT / "fixtures" / "launches.json")
    data = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("launches.json harus berupa daftar")
    return data


def fetch_binance_daily(symbol: str = "BTCUSDT", limit: int = 120) -> list[Bar]:
    """Public klines. No API key. Used only when the operator passes --fetch."""
    url = (
        "https://api.binance.com/api/v3/klines"
        f"?symbol={symbol}&interval=1d&limit={int(limit)}"
    )
    request = urllib.request.Request(url, headers={"User-Agent": "paired-desk"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    bars: list[Bar] = []
    for row in payload:
        # Binance returns [open time, open, high, low, close, ...]
        close_ms = int(row[6])
        date = _utc_date(close_ms)
        bars.append(Bar(date, float(row[4])))
    if len(bars) < 2:
        raise ValueError("Binance mengembalikan terlalu sedikit bar")
    return bars


def _utc_date(close_ms: int) -> str:
    import datetime as dt

    moment = dt.datetime.fromtimestamp(close_ms / 1000, dt.timezone.utc)
    return moment.date().isoformat()
