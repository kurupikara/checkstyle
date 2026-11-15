"""Command lines and config files for the upstream tools.

Builtin paper mode does not call these. Delegate and live-execute do, and only
with argv lists. Secrets stay in the environment.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from desk.config import Config

_TOKEN = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
_LIVE_FLAG = "I_UNDERSTAND"

ENGINES = (
    ("vibe", "vibe-trading", "HKUDS/Vibe-Trading", "Riset, backtest, dan jejak paper"),
    ("ai_hedge_fund", "aihf", "virattt/ai-hedge-fund", "Komite ekuitas dan buku paper"),
    ("hummingbot", "hbot", "hummingbot/hummingbot", "Eksekusi CEX, termasuk paper trade"),
    ("pumpfun", "pump_bot", "chainstacklabs/pumpfun-bonkfun-bot", "Launchpad Solana"),
    ("grok", "grok", "xai-org/grok-build", "Operator yang menjalankan meja ini"),
)


class HandoffError(RuntimeError):
    pass


def probe() -> list[dict]:
    rows = []
    for key, binary, repo, role in ENGINES:
        path = shutil.which(binary)
        rows.append(
            {
                "engine": key,
                "binary": binary,
                "repo": repo,
                "role": role,
                "installed": path is not None,
                "path": path or "",
            }
        )
    return rows


def require_token(label: str, value: str) -> str:
    if not _TOKEN.match(value):
        raise HandoffError(f"{label} harus token sederhana, diterima: {value!r}")
    return value


def aihf_mandate(cfg: Config) -> str:
    equities = [item.symbol for item in cfg.universe if item.kind == "equity" and item.symbol != "CHOP"]
    universe = ",".join(require_token("simbol", symbol) for symbol in equities) or "AAPL"
    capital = int(cfg.capital_usd)
    # Schema 2 is the public mandate format from ai-hedge-fund. Model names are
    # theirs; this file only points a paper fund at our equity sleeve.
    return f"""schema_version: 2
name: paired-desk
strategies:
  - name: deep-value
    blend: {{mode: long_only}}
    weight: 1.0
    models:
      - name: graham
        weight: 2.0
      - name: buffett
      - name: munger
risk:
  max_position_pct: {cfg.max_weight}
  max_gross_exposure: 1.0
  max_drawdown_pct: {cfg.portfolio_drawdown_halt}
capital: {capital}
rebalance: daily
benchmark: SPY
# Universe is not part of the mandate. Deploy with:
# aihf paper create paired-desk --mandate aihf-mandate.yaml --universe {universe}
"""


def aihf_argv(mandate: Path, universe: str) -> list[list[str]]:
    names = require_token("universe", universe.replace(",", ""))
    if not names:
        raise HandoffError("universe ekuitas kosong")
    return [
        [
            "aihf",
            "paper",
            "create",
            "paired-desk",
            "--mandate",
            str(mandate),
            "--universe",
            universe,
        ],
        ["aihf", "paper", "tick", "paired-desk"],
    ]


def hummingbot_argv(cfg: Config, pair: str, live: bool) -> list[str]:
    trading_pair = require_token("pair", pair)
    if live:
        if not cfg.live_exchange:
            raise HandoffError("isi live.exchange di desk.json sebelum eksekusi sungguhan")
        exchange = require_token("exchange", cfg.live_exchange)
    else:
        exchange = "binance_paper_trade"
    slug = trading_pair.replace("-", "").lower()
    return [
        "hbot",
        "deploy",
        "simple_pmm",
        "--name",
        f"conf_paired_{slug}.yml",
        "--set",
        f"exchange={exchange}",
        "--set",
        f"trading_pair={trading_pair}",
    ]


def pump_yaml(cfg: Config, enabled: bool) -> str:
    platform = require_token("platform", cfg.live_pump_platform)
    listener = require_token("listener", cfg.live_pump_listener)
    if listener not in {"logs", "blocks", "geyser", "shreds"}:
        raise HandoffError("listener pump tidak dikenal")
    if platform not in {"pump_fun", "launchlab", "lets_bonk", "stonk_fun"}:
        raise HandoffError("platform pump tidak dikenal")
    if platform != "pump_fun" and listener == "logs":
        raise HandoffError("listener logs hanya untuk pump_fun")
    amount = cfg.live_pump_buy
    if amount <= 0 or amount > 0.05:
        raise HandoffError("live pump_buy_amount_sol harus di (0, 0.05]")
    flag = "true" if enabled else "false"
    return f"""name: "paired-desk"
env_file: ".env"
rpc_endpoint: "${{SOLANA_NODE_RPC_ENDPOINT}}"
wss_endpoint: "${{SOLANA_NODE_WSS_ENDPOINT}}"
private_key: "${{SOLANA_PRIVATE_KEY}}"
enabled: {flag}
separate_process: true
platform: "{platform}"
trade:
  buy_amount: {amount}
  buy_slippage: 0.3
  sell_slippage: 0.3
  exit_strategy: "tp_sl"
  take_profit_percentage: {cfg.launch_take_profit}
  stop_loss_percentage: {cfg.launch_stop_loss}
  max_hold_time: 60
  price_check_interval: 2
  extreme_fast_mode: false
  entry: "new_launch"
filters:
  listener_type: "{listener}"
  max_token_age: {cfg.launch_max_age}
  marry_mode: false
  yolo_mode: false
retries:
  max_attempts: 1
  wait_after_creation: 15
  wait_after_buy: 15
  wait_before_new_token: 15
cleanup:
  mode: "after_sell"
  force_close_with_burn: false
node:
  max_rps: 25
"""


def pump_argv(config_path: Path) -> list[str]:
    return ["pump_bot", "--config", str(config_path)]


def grok_argv(prompt: str) -> list[str]:
    if not prompt.strip():
        raise HandoffError("prompt operator kosong")
    return ["grok", "-p", prompt, "--output-format", "streaming-json"]


def live_allowed() -> bool:
    return os.environ.get("PAIRED_DESK_LIVE") == _LIVE_FLAG


def assert_live_allowed() -> None:
    if not live_allowed():
        raise HandoffError(
            "Live tidak dijalankan. Set PAIRED_DESK_LIVE=I_UNDERSTAND di environment "
            "bila Anda sengaja ingin meneruskan order ke hbot atau pump_bot."
        )


def write_handoff(directory: Path, cfg: Config, enable_pump: bool) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    mandate = directory / "aihf-mandate.yaml"
    pump = directory / "pump.yaml"
    commands = directory / "commands.txt"
    mandate.write_text(aihf_mandate(cfg), encoding="utf-8")
    pump.write_text(pump_yaml(cfg, enabled=enable_pump), encoding="utf-8")
    equities = [item.symbol for item in cfg.universe if item.kind == "equity" and _TOKEN.match(item.symbol)]
    universe = ",".join(symbol for symbol in equities if symbol != "CHOP") or "AAPL"
    lines = [
        " ".join(part) for part in aihf_argv(mandate, universe)
    ]
    lines.append(" ".join(hummingbot_argv(cfg, cfg.live_pair, live=enable_pump and cfg.mode == "live")))
    lines.append(" ".join(pump_argv(pump)))
    commands.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"mandate": mandate, "pump": pump, "commands": commands}


def run_argv(argv: list[str]) -> tuple[int, str]:
    binary = shutil.which(argv[0])
    if binary is None:
        raise HandoffError(f"{argv[0]} tidak ada di PATH")
    completed = subprocess.run(
        [binary, *argv[1:]],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode, output.strip()
