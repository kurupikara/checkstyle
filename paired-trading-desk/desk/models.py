"""Shared records. Venues are the upstream roles, not exchange names."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Bar:
    date: str
    close: float


@dataclass
class ResearchCard:
    symbol: str
    venue: str
    bars: int
    total_return: float
    buy_hold_return: float
    excess_return: float
    max_drawdown: float
    signal: int
    fast: float | None
    slow: float | None
    passed: bool
    reason: str


@dataclass
class Vote:
    agent: str
    value: float
    note: str


@dataclass
class Decision:
    symbol: str
    venue: str
    action: str
    score: float
    target_weight: float
    reason: str
    votes: list[Vote] = field(default_factory=list)


@dataclass
class Position:
    symbol: str
    venue: str
    qty: float
    avg_price: float
    quote: str
