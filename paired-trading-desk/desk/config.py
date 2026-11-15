"""Load desk.json. The file is the only configuration surface."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Instrument:
    symbol: str
    kind: str
    venue: str


@dataclass(frozen=True)
class Config:
    mode: str
    capital_usd: float
    capital_sol: float
    risk_on_symbol: str
    universe: tuple[Instrument, ...]
    fast: int
    slow: int
    min_total_return: float
    max_drawdown: float
    min_vote: float
    max_weight: float
    max_order_usd: float
    max_gross_usd: float
    rebalance_band_usd: float
    max_open_launches: int
    portfolio_drawdown_halt: float
    fee_usd: float
    fee_sol: float
    launch_enabled: bool
    launch_platforms: tuple[str, ...]
    launch_buy_sol: float
    launch_max_age: float
    launch_take_profit: float
    launch_stop_loss: float
    launch_max_hold: int
    engines: dict[str, str]
    live_exchange: str
    live_pair: str
    live_pump_buy: float
    live_pump_platform: str
    live_pump_listener: str
    raw: dict

    def instrument(self, symbol: str) -> Instrument:
        for item in self.universe:
            if item.symbol == symbol:
                return item
        raise KeyError(symbol)


def load_config(path: Path | None = None) -> Config:
    file = path or (ROOT / "desk.json")
    raw = json.loads(file.read_text(encoding="utf-8"))
    research = raw["research"]
    committee = raw["committee"]
    risk = raw["risk"]
    fees = raw["fees_bps"]
    launch = raw["launch_lane"]
    live = raw["live"]
    universe = tuple(
        Instrument(item["symbol"], item["kind"], item["venue"]) for item in raw["universe"]
    )
    return Config(
        mode=raw.get("mode", "paper"),
        capital_usd=float(raw["capital_usd"]),
        capital_sol=float(raw["capital_sol"]),
        risk_on_symbol=raw["risk_on_symbol"],
        universe=universe,
        fast=int(research["fast"]),
        slow=int(research["slow"]),
        min_total_return=float(research["min_total_return"]),
        max_drawdown=float(research["max_drawdown"]),
        min_vote=float(committee["min_vote"]),
        max_weight=float(committee["max_weight"]),
        max_order_usd=float(risk["max_order_usd"]),
        max_gross_usd=float(risk["max_gross_usd"]),
        rebalance_band_usd=float(risk["rebalance_band_usd"]),
        max_open_launches=int(risk["max_open_launches"]),
        portfolio_drawdown_halt=float(risk["portfolio_drawdown_halt"]),
        fee_usd=float(fees["usd"]) / 10_000,
        fee_sol=float(fees["sol"]) / 10_000,
        launch_enabled=bool(launch["enabled"]),
        launch_platforms=tuple(launch["platforms"]),
        launch_buy_sol=float(launch["buy_amount_sol"]),
        launch_max_age=float(launch["max_token_age_seconds"]),
        launch_take_profit=float(launch["take_profit"]),
        launch_stop_loss=float(launch["stop_loss"]),
        launch_max_hold=int(launch["max_hold_steps"]),
        engines=dict(raw["engines"]),
        live_exchange=str(live.get("exchange") or ""),
        live_pair=str(live.get("trading_pair") or "BTC-USDT"),
        live_pump_buy=float(live.get("pump_buy_amount_sol") or 0.001),
        live_pump_platform=str(live.get("pump_platform") or "pump_fun"),
        live_pump_listener=str(live.get("pump_listener") or "logs"),
        raw=raw,
    )
