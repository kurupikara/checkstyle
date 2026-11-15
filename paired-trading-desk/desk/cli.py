"""Command line. The default path replays the fixture book and trades nothing live."""

from __future__ import annotations

import argparse
import os
import shutil
import sys

from desk.config import load_config
from desk.handoff import (
    HandoffError,
    assert_live_allowed,
    grok_argv,
    hummingbot_argv,
    probe,
    pump_argv,
    run_argv,
    write_handoff,
)
from desk.market import fetch_binance_daily, load_fixture_book
from desk.session import halt, load_report, resume, run_paper, state_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="desk",
        description="Meja trading paper yang memasangkan lima repositori sesuai perannya.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="putar ulang fixture dari awal")
    demo.add_argument("--fetch", action="store_true", help="ganti BTC-USDT dengan kline harian Binance")
    run = sub.add_parser("run", help="sama dengan demo, disimpan di var/paper")
    run.add_argument("--fetch", action="store_true")

    sub.add_parser("status", help="tampilkan laporan terakhir")
    sub.add_parser("doctor", help="cek mode, kill switch, dan binary upstream")

    halt_cmd = sub.add_parser("halt", help="tulis kill switch")
    halt_cmd.add_argument("--reason", default="dihentikan operator")
    sub.add_parser("resume", help="hapus kill switch")
    sub.add_parser("handoff", help="tulis config paper untuk aihf, hbot, dan pump_bot")

    sub.add_parser("live-plan", help="tulis config live tanpa mengirim order")
    sub.add_parser("live-execute", help="jalankan hbot dan pump_bot hanya jika live memang diizinkan")

    serve = sub.add_parser("serve", help="dashboard lokal")
    serve.add_argument("--port", type=int, default=8765)

    operator = sub.add_parser("operator", help="ringkasan meja; grok hanya jika diminta dan di-delegate")
    operator.add_argument("--ask", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            return _cycle("demo", args.fetch)
        if args.command == "run":
            return _cycle("paper", args.fetch)
        if args.command == "status":
            return _status()
        if args.command == "doctor":
            return _doctor()
        if args.command == "halt":
            halt(state_dir("paper"), args.reason)
            print(f"Kill switch aktif: {args.reason}")
            return 0
        if args.command == "resume":
            removed = resume(state_dir("paper"))
            print("Kill switch dilepas." if removed else "Kill switch memang tidak aktif.")
            return 0
        if args.command == "handoff":
            return _handoff(enable_pump=False)
        if args.command == "live-plan":
            return _live_plan()
        if args.command == "live-execute":
            return _live_execute()
        if args.command == "serve":
            from desk.web import serve as serve_app

            serve_app(args.port)
            return 0
        if args.command == "operator":
            return _operator(args.ask)
    except (HandoffError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print("Perintah tidak dikenal", file=sys.stderr)
    return 2


def _cycle(name: str, fetch: bool) -> int:
    series = load_fixture_book()
    if fetch:
        series["BTC-USDT"] = fetch_binance_daily("BTCUSDT")
        print(f"BTC-USDT memakai {len(series['BTC-USDT'])} bar Binance.")
    report = run_paper(state_dir(name), series=series, reset=True)
    print(format_report(report))
    print(f"Laporan: var/{name}/report.json")
    return 0


def _status() -> int:
    report = load_report(state_dir("paper")) or load_report(state_dir("demo"))
    if report is None:
        print("Belum ada siklus. Jalankan: python3 paired-desk demo")
        return 0
    print(format_report(report))
    return 0


def _doctor() -> int:
    cfg = load_config()
    print(f"mode: {cfg.mode}")
    print(f"mesin: {cfg.engines}")
    kill = state_dir("paper") / "KILL"
    print(f"kill switch: {kill.read_text().strip() if kill.exists() else 'tidak aktif'}")
    print(f"live flag: {'ada' if os.environ.get('PAIRED_DESK_LIVE') else 'tidak di-set'}")
    for row in probe():
        mark = "siap" if row["installed"] else "builtin"
        print(f"{row['engine']:16} {mark:8} {row['role']}  ({row['repo']})")
    print("Paper bawaan tidak membutuhkan binary di atas.")
    return 0


def _handoff(enable_pump: bool) -> int:
    cfg = load_config()
    paths = write_handoff(state_dir("handoff"), cfg, enable_pump=enable_pump)
    print("File handoff:")
    for path in paths.values():
        print(f"  {path}")
    print(paths["commands"].read_text(encoding="utf-8"))
    return 0


def _live_plan() -> int:
    assert_live_allowed()
    cfg = load_config()
    if cfg.mode != "live":
        raise HandoffError("ubah desk.json mode menjadi live sebelum menulis rencana live")
    return _handoff(enable_pump=True)


def _live_execute() -> int:
    assert_live_allowed()
    cfg = load_config()
    if cfg.mode != "live":
        raise HandoffError("desk.json masih mode paper, tidak ada order yang dikirim")
    paths = write_handoff(state_dir("handoff"), cfg, enable_pump=True)
    pair_cmd = hummingbot_argv(cfg, cfg.live_pair, live=True)
    pump_cmd = pump_argv(paths["pump"])
    for argv in (pair_cmd, pump_cmd):
        if shutil.which(argv[0]) is None:
            raise HandoffError(f"{argv[0]} tidak terpasang, order tidak dikirim")
        code, output = run_argv(argv)
        print(output)
        if code != 0:
            raise HandoffError(f"{argv[0]} keluar dengan status {code}")
    return 0


def _operator(ask: bool) -> int:
    path = state_dir("paper")
    report = load_report(path)
    if report is None:
        report = run_paper(path, reset=True)
    text = format_report(report)
    print(text)
    cfg = load_config()
    if not ask or cfg.engines.get("grok") != "delegate":
        print("Operator bawaan selesai. Grok tidak dipanggil.")
        return 0
    prompt = (
        "Kamu operator paired desk. Jangan mengirim order live. "
        "Ringkas laporan paper ini dan sebut risiko yang masih terbuka:\n" + text
    )
    code, output = run_argv(grok_argv(prompt))
    print(output)
    return 0 if code == 0 else code


def format_report(report: dict) -> str:
    lines = [
        "Paired desk — siklus paper",
        f"Ekuitas USD {report['equity_usd']:.2f} | kas USD {report['cash_usd']:.2f} | kas SOL {report['cash_sol']:.6f}",
    ]
    if report.get("killed"):
        lines.append(f"Kill switch: {report['killed']}")
    if report.get("drawdown_halt"):
        lines.append("Perdagangan berhenti karena drawdown portofolio.")
    lines.append("")
    lines.append("Riset (Vibe-Trading)")
    for card in report.get("research", {}).values():
        mark = "lolos" if card["passed"] else "ditolak"
        lines.append(
            f"  {card['symbol']:12} {mark:7} imbal {card['total_return']:.2%}  "
            f"drawdown {card['max_drawdown']:.2%}  {card['reason']}"
        )
    lines.append("")
    lines.append("Komite (AI Hedge Fund)")
    decisions = report.get("decisions") or {}
    if not decisions:
        lines.append("  tidak ada nama yang lolos gerbang")
    for decision in decisions.values():
        lines.append(
            f"  {decision['symbol']:12} {decision['action']:4} skor {decision['score']:+.2f}  {decision['reason']}"
        )
    lines.append("")
    lines.append("Posisi")
    positions = report.get("positions") or []
    if not positions:
        lines.append("  kosong")
    for position in positions:
        lines.append(
            f"  {position['symbol']:12} {position['venue']:16} qty {position['qty']:.6f} @ {position['avg_price']:.4f}"
        )
    lines.append("")
    lines.append("Launchpad (pumpfun / letsbonk)")
    for launch in report.get("launches", []):
        pnl = launch.get("pnl_sol", 0.0)
        lines.append(
            f"  {launch['symbol']:8} {launch['platform']:12} {launch['status']:8} {launch['reason']:16} pnl {pnl:+.6f} SOL"
        )
    lines.append("")
    lines.append(f"Isi {len(report.get('fills', []))} fill. Eksekusi CEX memakai jalur Hummingbot; ekuitas memakai buku paper komite.")
    return "\n".join(lines)

